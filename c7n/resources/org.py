# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from concurrent.futures import as_completed
import json
import logging
import os
import threading

from botocore.exceptions import ClientError

from c7n.actions import Action
from c7n.credentials import assumed_session
from c7n.exceptions import PolicyValidationError
from c7n.filters import Filter, ValueFilter, ListItemFilter
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.resources.aws import AWS
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema


log = logging.getLogger("custodian.org-accounts")

ORG_ACCOUNT_SESSION_NAME = "CustodianOrgAccount"


class OrgAccess:
    org_session = None

    def parse_access_role(self):
        params = {}
        for q in self.data.get("query", ()):
            params.update(q)
        return params.get("org-access-role")

    def get_org_session(self):
        # so we have to do a three way dance
        # cli role -> (optional org access role) -> target account role
        #
        # in lambda though if we have a member-role we're effectively
        # already in the org root on the event.
        #
        if self.org_session:
            return self.org_session
        org_access_role = self.parse_access_role()
        if org_access_role and not (
            "LAMBDA_TASK_ROOT" in os.environ and self.data.get("mode", {}).get("member-role")
        ):
            self.org_session = assumed_session(
                role_arn=org_access_role,
                session_name=ORG_ACCOUNT_SESSION_NAME,
                region=self.session_factory.region,
                session=local_session(self.session_factory),
            )
        else:
            self.org_session = local_session(self.session_factory)
        return self.org_session


@AWS.resources.register("org-policy")
class OrgPolicy(QueryResourceManager, OrgAccess):
    policy_types = (
        "SERVICE_CONTROL_POLICY",
        "TAG_POLICY",
        "BACKUP_POLICY",
        "AISERVICES_OPT_OUT_POLICY",
    )

    class resource_type(TypeInfo):
        service = "organizations"
        id = "Id"
        name = "Name"
        arn = "Arn"
        arn_type = "policy"
        enum_spec = ("list_policies", "Policies", None)
        global_resource = True
        permissions_augment = ("organizations:ListTagsForResource",)
        universal_augment = object()

    def resources(self, query=None):
        q = self.parse_query()
        if query is not None:
            q.update(query)
        else:
            query = q
        return super().resources(query=query)

    def augment(self, resources):
        return universal_augment(self, resources)

    def parse_query(self, query=None):
        params = {}
        for q in self.data.get("query", ()):
            if isinstance(q, dict) and "filter" in q:
                params["Filter"] = q["filter"]
        if not params:
            params["Filter"] = "SERVICE_CONTROL_POLICY"
        return params


class DescribeUnit(DescribeSource):
    org_type = "ORGANIZATIONAL_UNIT"

    def get_permissions(self):
        m = self.manager.get_model()
        return list(m.permissions_augment)

    def resources(self, query=None):
        if query is None:
            query = {}
        client = local_session(self.manager.session_factory).client("organizations")
        if "ParentId" not in query:
            query["ParentId"] = client.list_roots().get("Roots", ())[0].get("Id")
        ous = {}
        self.fetch_ous(client, query["ParentId"], ous, [query["ParentId"]])
        return universal_augment(self.manager, list(ous.values()))

    def fetch_ous(self, client, parent_id, units, stack):
        pager = client.get_paginator("list_children")
        ou_ids = [
            o["Id"]
            for o in pager.paginate(ParentId=parent_id, ChildType=self.org_type)
            .build_full_result()
            .get("Children")
        ]
        for ou_id in ou_ids:
            units[ou_id] = ou = client.describe_organizational_unit(
                OrganizationalUnitId=ou_id,
            )["OrganizationalUnit"]
            ou["Parents"] = list(stack)
            stack.append(ou_id)
            ou["Path"] = "/".join([units[p]["Name"] for p in stack if p.startswith("ou")])
            self.fetch_ous(client, ou_id, units, stack)
            stack.pop(-1)


@AWS.resources.register("org-unit")
class OrgUnit(QueryResourceManager):
    class resource_type(TypeInfo):
        service = "organizations"
        arn = "Arn"
        arn_type = "ou"
        name = "Name"
        id = "Id"
        global_resource = True
        permissions_augment = (
            "organizations:ListChildren",
            "organizations:DescribeOrganizationalUnit",
            "organizations:ListTagsForResource",
        )
        universal_augment = object()

    source_mapping = {"describe": DescribeUnit}


@AWS.resources.register("org-account")
class OrgAccount(QueryResourceManager, OrgAccess):
    class resource_type(TypeInfo):
        service = "organizations"
        id = "Id"
        name = "Name"
        arn = "Arn"
        arn_type = "account"
        enum_spec = ("list_accounts", "Accounts", None)
        global_resource = True
        permissions_augment = ("organizations:ListTagsForResource",)
        universal_augment = object()

    org_session = None

    def augment(self, resources):
        return universal_augment(self, resources)

    def validate(self):
        self.parse_query()
        return super().validate()

    def parse_query(self):
        params = {}
        for q in self.data.get("query", ()):
            params.update(q)
        self.account_config = {
            k: v for k, v in params.items() if k in ("org-access-role", "org-account-role")
        }
        if "org-account-role" not in self.account_config:
            # Default Organizations Role
            self.account_config["org-account-role"] = "OrganizationAccountAccessRole"

            # Default Organizations Role with Control Tower
            if os.environ.get("AWS_CONTROL_TOWER_ORG"):
                self.account_config["org-account-role"] = "AWSControlTowerExecution"


@OrgUnit.filter_registry.register("policy")
@OrgAccount.filter_registry.register("policy")
class PolicyFilter(ListItemFilter):
    schema = type_schema(
        "policy",
        required=["policy-type"],
        **{
            "policy-type": {"enum": OrgPolicy.policy_types},
            "inherited": {"type": "boolean"},
            "attrs": {"$ref": "#/definitions/filters_common/list_item_attrs"},
            "count": {"type": "number"},
            "count_op": {"$ref": "#/definitions/filters_common/comparison_operators"},
        },
    )

    permissions = ("organizations:ListRoots", "organizations:ListPoliciesForTarget")

    annotate_items = True
    item_annotation_key = "c7n:PolicyMatches"
    target_policies = None
    ou_root = None
    client = None

    def process(self, resources, event):
        self.client = local_session(self.manager.session_factory).client("organizations")
        if self.data.get("inherited") and self.manager.type == "org-account":
            # Get ou account hierarchy / parents
            hierarchy_manager = self.manager.get_resource_manager(
                "org-account", {"filters": ["org-unit"]}
            )

            ou_assembly = hierarchy_manager.filters[0]
            ou_assembly.ou_map = {
                ou["Id"]: ou for ou in self.manager.get_resource_manager("org-unit").resources()
            }
            ou_assembly.process_accounts(resources, event)
            # also initialize root for accounts as we dont store it as a parent.
            self.ou_root = self.client.list_roots()["Roots"][0]
        self.target_policies = {}
        return super().process(resources, event)

    def get_targets(self, resource):
        if not self.data.get("inherited"):
            yield resource["Id"]
            return

        # handle ous
        if self.manager.type == "org-unit":
            yield resource["Id"]
            for p in resource["Parents"]:
                yield p
            return

        # handle accounts
        yield resource["Id"]
        for p in resource[OrgUnitFilter.annotation_parent_key]:
            yield p["Id"]

        # finally the root
        yield self.ou_root["Id"]

    def get_item_values(self, resource):
        rpolicies = {}
        for tgt_id in self.get_targets(resource):
            if tgt_id not in self.target_policies:
                policies = self.client.list_policies_for_target(
                    Filter=self.data["policy-type"], TargetId=tgt_id
                ).get("Policies", ())
                self.target_policies[tgt_id] = policies
            for p in self.target_policies[tgt_id]:
                rpolicies[p["Id"]] = p
        return list(rpolicies.values())


@OrgAccount.action_registry.register("set-policy")
@OrgUnit.action_registry.register("set-policy")
class SetPolicy(Action):
    """Set a policy on an org unit or account

    .. code-block:: yaml

        policies:
          - name: attach-existing-scp
            resource: aws.org-unit
            filters:
              - type: policy
                policy-type: SERVICE_CONTROL_POLICY
                count: 0
                attrs:
                  - Name: RestrictedRootAccount
            actions:
              - type: set-policy
                policy-type: SERVICE_CONTROL_POLICY
                name: RestrictedRootAccount

    .. code-block:: yaml

        policies:
          - name: create-and-attach-scp
            resource: aws.org-unit
            filters:
              - type: policy
                policy-type: SERVICE_CONTROL_POLICY
                count: 0
                attrs:
                  - Name: RestrictedRootAccount
            actions:
              - type: set-policy
                policy-type: SERVICE_CONTROL_POLICY
                name: RestrictedRootAccount
                contents:
                  Version: "2012-10-17"
                  Statement:
                    - Sid: RestrictEC2ForRoot
                      Effect: Deny
                      Action:
                        - "ec2:*"
                      Resource:
                        - "*"
                      Condition:
                        StringLike:
                          "aws:PrincipalArn":
                            - arn:aws:iam::*:root
    """

    schema = type_schema(
        "set-policy",
        required=["name", "policy-type"],
        **{
            "name": {"type": "string"},
            "description": {"type": "string"},
            "policy-type": {"enum": OrgPolicy.policy_types},
            "contents": {"type": "object"},
            "tags": {"$ref": "#/definitions/string_dict"},
        },
    )
    permissions = ("organizations:AttachPolicy", "organizations:CreatePolicy")

    def process(self, resources):
        client = local_session(self.manager.session_factory).client("organizations")
        pid = self.ensure_scp(client)
        for r in resources:
            self.manager.retry(client.attach_policy, TargetId=r["Id"], PolicyId=pid)

    def ensure_scp(self, client):
        pmanager = self.manager.get_resource_manager(
            "org-policy", {"query": [{"filter": self.data["policy-type"]}]}
        )
        policies = pmanager.resources()
        found = False
        for p in policies:
            if p["Name"] == self.data["name"]:
                found = p
                break
        if found:
            # todo: perhaps modify/compare to match.
            return found["Id"]
        elif not self.data.get("contents"):
            raise PolicyValidationError(
                "Policy references not existent org policy " "without specifying contents"
            )
        ptags = [{"Key": k, "Value": v} for k, v in self.data.get("tags", {}).items()]
        ptags.append({"Key": "managed-by", "Value": "CloudCustodian"})
        response = client.create_policy(
            Name=self.data["name"],
            Description=self.data.get("description", "%s (custodian managed)" % self.data["name"]),
            Type=self.data["policy-type"],
            Content=json.dumps(self.data["contents"]),
            Tags=ptags,
        )
        return response["Policy"]["PolicySummary"]["Id"]


@OrgUnit.filter_registry.register("org-unit")
@OrgAccount.filter_registry.register("org-unit")
class OrgUnitFilter(ValueFilter):
    """Filter resources by their containment within an ou.

    .. code-block:: yaml

        policies:
          - name: org-units-by-parent-ou
            resource: aws.org-unit
            filters:
              - type: org-unit
                key: Name
                value: dev

          - name: org-accounts-by-parent-ou
            resource: aws.org-account
            filters:
              - type: org-unit
                key: Name
                value: dev
    """

    schema = type_schema("org-unit", rinherit=ValueFilter.schema)
    annotation_parent_key = "c7n:parents"
    ou_map = None
    permissions = OrgUnit.resource_type.permissions_augment

    def process(self, resources, event=None):
        self.ou_map = {
            ou["Id"]: ou for ou in self.manager.get_resource_manager("org-unit").resources()
        }
        if self.manager.type == "org-account":
            self.process_accounts(resources, event)
        return super().process(resources, event)

    def process_accounts(self, resources, event):
        client = local_session(self.manager.session_factory).client("organizations")
        for r in resources:
            if self.annotation_parent_key in r:
                continue
            # list parents only returns the immediate parent
            parents = []
            parent_info = client.list_parents(ChildId=r["Id"]).get("Parents").pop()
            if parent_info["Type"] == "ROOT":
                r[self.annotation_parent_key] = []
                continue
            parent = self.ou_map[parent_info["Id"]]
            parents.append(parent)
            while parent["Parents"]:
                next_p = parent["Parents"][-1]
                if next_p.startswith("r-"):
                    break
                parent = self.ou_map[next_p]
                parents.append(parent)
            r[self.annotation_parent_key] = parents
        return super().process(resources, event)

    def __call__(self, r):
        if self.manager.type == "org-unit":
            # we annotate parents as we walk down the tree, allowing us to reuse
            # the information for heirarchy filters.
            for pid in r["Parents"]:
                if pid.startswith("ou-") and super().__call__(self.ou_map[pid]):
                    return True
            return False
        else:
            for parent in r[self.annotation_parent_key]:
                if super().__call__(parent):
                    return True
            return False


class AccountHierarchy:
    def get_accounts_for_ous(self, client, ous):
        """get a set of accounts for the given ous ids"""
        account_ids = set()
        for o in ous:
            pager = client.get_paginator("list_children")
            for page in pager.paginate(ParentId=o, ChildType="ACCOUNT"):
                account_ids.update(a["Id"] for a in page.get("Children", []))
        return account_ids

    def get_ous_for_roots(self, client, roots):
        """Walk down the tree from the listed ou roots to collect all nested ous."""
        folders = set(roots)

        while roots:
            r = roots.pop(0)
            pager = client.get_paginator("list_children")
            for page in pager.paginate(ParentId=r, ChildType="ORGANIZATIONAL_UNIT"):
                roots.extend([f["Id"] for f in page.get("Children", [])])
                folders.update([f["Id"] for f in page.get("Children", [])])
        return folders


@OrgAccount.filter_registry.register("ou")
class OrganizationUnit(Filter, AccountHierarchy):
    schema = type_schema("ou", units={"type": "array", "items": {"type": "string"}})
    permissions = ("organizations:ListChildren",)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client("organizations")
        ous = self.get_ous_for_roots(client, self.data["units"])
        account_ids = self.get_accounts_for_ous(client, ous)
        results = []
        for r in resources:
            if r["Id"] not in account_ids:
                continue
            results.append(r)
        return results


class ProcessAccountSet:
    def resolve_regions(self, account, session):
        return self.data.get("regions", ("us-east-1",))

    def process_account_region(self, account, region, session):
        raise NotImplementedError()

    def process_account(self, account, session):
        log.info(
            "%s processing account:%s id:%s",
            self.type,
            account["Name"],
            account["Id"],
        )
        region_results = {}
        for r in self.resolve_regions(account, session):
            try:
                region_results[r] = self.process_account_region(account, r, session)
            except Exception as e:
                log.exception(
                    "%s account region error %s %s %s error: %s",
                    self.type,
                    account["Name"],
                    account["Id"],
                    r,
                    e,
                )
                region_results[r] = False
        return region_results

    def process_account_set(self, resources):
        account_results = {}
        org_session = self.manager.get_org_session()

        with self.manager.executor_factory(max_workers=8) as w:
            futures = {}
            for a in resources:
                try:
                    s = account_session(
                        org_session, a, self.manager.account_config["org-account-role"]
                    )
                except ClientError:
                    log.error(
                        "%s - error role assuming into %s:%s using role:%s",
                        self.type,
                        a["Name"],
                        a["Id"],
                        self.manager.account_config["org-account-role"],
                    )
                    continue
                futures[w.submit(self.process_account, a, s)] = a
            for f in as_completed(futures):
                a = futures[f]
                if f.exception():
                    log.error(
                        "%s - error in account:%s id:%s error:%s",
                        self.type,
                        a["Name"],
                        a["Id"],
                        f.exception(),
                    )
                    continue
                account_results[a["Id"]] = f.result()
        return account_results


@OrgAccount.filter_registry.register("cfn-stack")
class StackFilter(Filter, ProcessAccountSet):
    schema = type_schema(
        "cfn-stack",
        stack_names={"type": "array", "elements": {"type": "string"}},
        present={"type": "boolean"},
        status={
            "type": "array",
            "items": {
                "enum": [
                    "CREATE_IN_PROGRESS",
                    "CREATE_FAILED",
                    "CREATE_COMPLETE",
                    "ROLLBACK_IN_PROGRESS",
                    "ROLLBACK_FAILED",
                    "ROLLBACK_COMPLETE",
                    "DELETE_IN_PROGRESS",
                    "DELETE_FAILED",
                    "DELETE_COMPLETE",
                    "UPDATE_IN_PROGRESS",
                    "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS",
                    "UPDATE_COMPLETE",
                    "UPDATE_ROLLBACK_IN_PROGRESS",
                    "UPDATE_ROLLBACK_FAILED",
                    "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS",
                    "UPDATE_ROLLBACK_COMPLETE",
                    "REVIEW_IN_PROGRESS",
                    "IMPORT_IN_PROGRESS",
                    "IMPORT_COMPLETE",
                    "IMPORT_ROLLBACK_IN_PROGRESS",
                    "IMPORT_ROLLBACK_FAILED",
                    "IMPORT_ROLLBACK_COMPLETE",
                ]
            },
        },
        regions={"type": "array", "elements": {"type": "string"}},
    )

    permissions = ("sts:AssumeRole", "cloudformation:DescribeStacks")
    annotation = "c7n:cfn-stack"

    def process(self, resources, event=None):
        fresources = []
        results = self.process_account_set(resources)
        for r in resources:
            if r["Id"] not in results:
                continue
            if not any(results[r["Id"]].values()):
                continue
            fresults = {rk: rv for rk, rv in results[r["Id"]].items() if rv}
            r[self.annotation] = fresults
            fresources.append(r)
        return fresources

    def process_account_region(self, account, region, session):
        client = session.client("cloudformation", region_name=region)
        present = self.data.get("present", False)
        states = self.data.get("status", ())

        found = True
        for s in self.data.get("stack_names", ()):
            try:
                stacks = client.describe_stacks(StackName=s).get("Stacks", [])
                if states and stacks[0]["StackStatus"] not in states:
                    found = False
            except ClientError:
                found = False
            else:
                if not stacks:
                    found = False
        if present and found:
            return True
        elif not present and not found:
            return True
        return False


ACCOUNT_SESSION = threading.local()


def account_session(org_session, account, role):
    # differs from local session in being account aware
    # note we expect users of these session to explicitly
    # construct clients by region, as the session as
    # the cache is not region aware.
    #
    # TODO: add cache timeouts.
    if role.startswith("arn"):
        role = role.format(org_account_id=account["Id"])
    else:
        role = f"arn:aws:iam::{account['Id']}:role/{role}"

    org_accounts = getattr(ACCOUNT_SESSION, "org_accounts", {})
    if role in org_accounts:
        return org_accounts[role]

    s = assumed_session(
        role_arn=role,
        session_name=ORG_ACCOUNT_SESSION_NAME,
        session=org_session,
        region=org_session.region_name,
    )

    org_accounts[role] = s
    setattr(ACCOUNT_SESSION, "org_accounts", org_accounts)
    return s
