# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from concurrent.futures import as_completed
import copy
import json
import pytz
from c7n.exceptions import PolicyValidationError
from c7n.utils import chunks, type_schema
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager, DescribeSource
from c7n_tencentcloud.utils import isoformat_datetime_str, PageMethod, convert_date_str
from c7n.filters import ValueFilter, Filter


class DescribeCAM(DescribeSource):
    """DescribeCAM"""
    def get_resource_qcs(self, resources):
        qcs_list = []

        # for CAM, there is no region in qcs
        for r in resources:
            qcs = self.get_qcs(self.resource_type.service,
                               "",
                               self.resource_manager.config.account_id,
                               self.resource_type.resource_prefix,
                               r[self.resource_type.id])
            qcs_list.append(qcs)
        return qcs_list


@resources.register("cam-user")
class User(QueryResourceManager):
    """
    User - user management in Cloud Access Management (CAM)
    https://www.tencentcloud.com/document/product/1021/37656

    :example:

    .. code-block:: yaml

        policies:
        - name: cam-too-old-users
          resource: tencentcloud.cam-user
          filters:
          - type: value
            key: CreateTime
            value_type: age
            value: 7000
            op: less-than
    """
    source_mapping = {"describe": DescribeCAM}

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "Uin"
        endpoint = "cam.tencentcloudapi.com"
        service = "cam"
        version = "2019-01-16"
        enum_spec = ("ListUsers", "Response.Data[]", {})
        taggable = True
        resource_prefix = "uin"
        batch_size = 10
        datetime_fields_format = {
            "CreateTime": ("%Y-%m-%d %H:%M:%S", pytz.timezone("Asia/Shanghai")),
            "LastLoginTime": ("%Y-%m-%d %H:%M:%S", pytz.timezone("Asia/Shanghai")),
            "access_keys.CreateTime": ("%Y-%m-%d %H:%M:%S", pytz.timezone("Asia/Shanghai")),
            "access_keys.LastUsedDate": ("%Y-%m-%d", pytz.timezone("Asia/Shanghai"))
        }

    def __init__(self, ctx, data):
        super().__init__(ctx, data)
        self._query_client = None

    @property
    def client(self):
        """client"""
        if self._query_client is None:
            self._query_client = self.get_client()
        return self._query_client

    def augment(self, resources):
        """augment"""
        for item in resources:
            fm = self.resource_type.datetime_fields_format["CreateTime"]
            item["CreateTime"] = isoformat_datetime_str(item["CreateTime"], fm[0], fm[1])
        return resources


@User.filter_registry.register('group')
class GroupMembership(ValueFilter):
    """
    Filter based on users' group.
    Official doc: https://www.tencentcloud.com/document/product/598/33380
    Use limit: https://www.tencentcloud.com/document/product/598/10609

    :example:

    .. code-block:: yaml

        policies:
        - name: cam-user-missing-group
          resource: tencentcloud.cam-user
          filters:
          - type: group
            key: GroupName
            value:
    """
    schema = type_schema('group', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ()
    group_field_name = "c7n:Groups"

    def get_user_groups(self, user_set):
        """get_user_groups"""
        for user in user_set:
            params = {
                # we can only create no more than 300 groups
                # and one sub-account can only belong to 10 user groups at most
                "Rp": 300,
                "SubUin": user[self.manager.resource_type.id]
            }
            resp = self.manager.client.execute_query("ListGroupsForUser", params)
            user[self.group_field_name] = resp["Response"]["GroupInfo"]

    def process(self, resources, event=None):
        """process"""
        # get users' group
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for user_set in chunks([r for r in resources if self.group_field_name not in r]):
                futures.append(w.submit(self.get_user_groups, user_set))
            for f in as_completed(futures):
                pass

        matched = []
        for r in resources:
            groups = r.get(self.group_field_name, [])
            if self.data.get("value") in ["absent", None]:
                # for below usecase:
                #   - type: group
                #     key: GroupName
                #     value: null
                if not groups:
                    matched.append(r)
            else:
                for group in groups:
                    if self.match(group) and r not in matched:
                        matched.append(r)
        return matched


@User.filter_registry.register('credential')
class CredentialFilter(Filter):
    """CredentialFilter
    :example:

    .. code-block:: yaml

        policies:
        - name: cam-user-access-key-rotation
          resource: tencentcloud.cam-user
          filters:
          - type: credential
            key: access_keys.CreateTime
            value_type: age
            value: 3
            op: greater-than
          - type: credential
            key: access_keys.Status
            value: Active
        - name: cam-user-mfa-missing
          resource: tencentcloud.cam-user
          filters:
          - type: credential
            key: ConsoleLogin
            value: 1
          - type: credential
            key: login_mfa_active
            value: false
    """
    schema = type_schema(
        'credential',
        value_type={'$ref': '#/definitions/filters_common/value_types'},
        key={'type': 'string',
             'enum': [
                 'ConsoleLogin',
                 'LastLoginTime',
                 'login_mfa_active',
                 'access_keys',
                 'access_keys.Status',
                 'access_keys.LastUsedDate',
                 'access_keys.CreateTime',
             ]},
        value={'$ref': '#/definitions/filters_common/value'},
        op={'$ref': '#/definitions/filters_common/comparison_operators'})

    permissions = ()

    # for access keys only
    matched_annotation_key = 'c7n:matched-keys'

    # identify whether the resource is in the process of credential filter
    filter_in_progress_flag = "c7n:tencentcloud-credential"
    filter_matched_flag = "c7n:tencentcloud-matched"

    def set_user_login_mfa_active(self, resource):
        """set_user_login_mfa_active"""
        params = {"SubUin": resource[self.manager.resource_type.id]}
        resp = self.manager.client.execute_query("DescribeSafeAuthFlagColl", params)
        mfa_flag = resp["Response"]["LoginFlag"]

        # https://www.tencentcloud.com/document/api/598/32230#LoginActionFlag
        # several kinds of mfa, mfa is active if any of them is set
        resource["c7n:login_mfa_active"] = any([v for _, v in mfa_flag.items()])

    def set_user_access_keys(self, resource):
        """set_user_access_keys"""
        params = {"TargetUin": resource[self.manager.resource_type.id]}
        resp = self.manager.client.execute_query("ListAccessKeys", params)
        access_keys = resp["Response"]["AccessKeys"]
        if access_keys:
            # get keys' last used time
            for batch in chunks(access_keys, 10):
                params = {
                    "SecretIdList": [it["AccessKeyId"] for it in batch]
                }
                data = self.manager.client.execute_query("GetSecurityLastUsed", params)
                for idx, v in enumerate(data["Response"]["SecretIdLastUsedRows"]):
                    if v["LastUsedDate"]:
                        fm = self.manager.resource_type.\
                            datetime_fields_format["access_keys.LastUsedDate"]
                        batch[idx]["LastUsedDate"] = convert_date_str(v["LastUsedDate"],
                                                                      fm[0], fm[1])
                    # pre-process for filter
                    fm = self.manager.resource_type.datetime_fields_format["access_keys.CreateTime"]
                    batch[idx]["CreateTime"] = isoformat_datetime_str(batch[idx]["CreateTime"],
                                                                      fm[0], fm[1])
        resource["c7n:access_keys"] = access_keys

    def set_user_last_login_time(self, resources):
        """set_user_last_login_time"""
        for batch in chunks(resources, 50):
            uins = [r[self.manager.resource_type.id] for r in batch]
            params = {
                "FilterSubAccountUin": uins
            }
            resp = self.manager.client.execute_query("DescribeSubAccounts", params)
            uin_map = {r["Uin"]: r for r in resp["Response"]["SubAccounts"]}
            for resource in batch:
                uin = resource[self.manager.resource_type.id]
                if uin in uin_map:
                    fm = self.manager.resource_type.datetime_fields_format["LastLoginTime"]
                    resource["LastLoginTime"] = \
                        isoformat_datetime_str(uin_map[uin]["LastLoginTime"], fm[0], fm[1])

    def pre_process(self, resources):
        """pre_process"""
        key = self.data["key"]
        if key == "login_mfa_active":
            for resource in resources:
                self.set_user_login_mfa_active(resource)
        if key == "LastLoginTime":
            # using last login time
            self.set_user_last_login_time(resources)
        if "access_keys" in key:
            for resource in resources:
                if "c7n:access_keys" not in resource:
                    self.set_user_access_keys(resource)

    def process_access_key_filter(self, resource):
        """process_access_key_filter"""
        # access_keys filter
        matcher_config = copy.deepcopy(self.data)

        # here key_coll = "c7n:access_keys"
        key_coll, matcher_config["key"] = self.data["key"].split(".", 1)
        key_coll = f"c7n:{key_coll}"
        v_filter = ValueFilter(matcher_config)
        v_filter.annotate = False

        k_matched = []
        block_op = self.get_block_operator()
        if block_op == "and":
            init_flag = False
            if self.filter_in_progress_flag not in resource:
                resource[self.filter_in_progress_flag] = True
                init_flag = True

            for it in resource[key_coll]:
                if v_filter.match(it):
                    if init_flag:
                        # the first filter
                        k_matched.append(it)
                        it[self.filter_matched_flag] = 'credential'
                    else:
                        if self.filter_matched_flag in it:
                            # for the "and" case
                            # we need to check if it satisfies the former filter
                            k_matched.append(it)
                else:
                    if not init_flag and self.filter_matched_flag in it:
                        # for the "and" case
                        # if not match the filter, we need to clear the annotation
                        it.pop(self.filter_matched_flag)
        else:
            for it in resource[key_coll]:
                if v_filter.match(it):
                    k_matched.append(it)

        # for further filter like:
        # - type: value
        #   key: 'length("c7n:matched-keys")'
        #   value: 2
        self.merge_annotation(resource, self.matched_annotation_key, k_matched)
        return bool(k_matched)

    def process(self, resources, event=None):
        """process"""
        self.pre_process(resources)

        key = self.data["key"]
        results = []
        for resource in resources:
            if key in ["ConsoleLogin", "LastLoginTime"]:
                v_filter = ValueFilter(self.data)
                if v_filter.match(resource):
                    results.append(resource)
            elif key in ["login_mfa_active"]:
                f_data = copy.deepcopy(self.data)
                f_data["key"] = f"c7n:{key}"
                v_filter = ValueFilter(f_data)
                if v_filter.match(resource):
                    results.append(resource)
            elif 'access_keys' in key:
                if self.process_access_key_filter(resource):
                    results.append(resource)

        return results


class DescribePolicy(DescribeCAM):
    """DescribePolicy"""
    def augment(self, resources):
        """
        Policy don't have tags.
        If we try getting policy's tags, tencentcloud api will return error.
        """
        return resources


@resources.register("cam-policy")
class Policy(QueryResourceManager):
    """
    Policy - Policy management in Cloud Access Management (CAM)
    https://www.tencentcloud.com/document/product/1021/37656

    :example:

    .. code-block:: yaml

        policies:
        - name: cam-policy-overly-permissive
          resource: tencentcloud.cam-policy
          filters:
          - or:
            - type: has-allow-all
            - type: check-permissions
              match: allowed
              actions:
              - "*:*"
    """
    source_mapping = {"describe": DescribePolicy}

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "PolicyId"
        endpoint = "cam.tencentcloudapi.com"
        service = "cam"
        version = "2019-01-16"
        enum_spec = ("ListPolicies", "Response.List[]", {})
        taggable = False
        resource_prefix = "policyid"
        paging_def = {"method": PageMethod.Page, "limit": {"key": "Rp", "value": 200}}

    def get_resource_query_params(self):
        """get_resource_query_params"""
        params = super().get_resource_query_params()
        # only get custom plicies
        params["Scope"] = "Local"
        return params

    def get_policy_binded_entities(self, resource):
        """get_policy_used_entities"""
        params = {"PolicyId": resource[self.resource_type.id]}
        resp = self.get_client().execute_query("ListEntitiesForPolicy", params)
        resource["binded_entities"] = resp["Response"]["List"]

    def get_policy_content(self, resource):
        """get_policy_content"""
        cli = self.get_client()
        params = {"PolicyId": resource[self.resource_type.id]}
        resp = cli.execute_query("GetPolicy", params)
        resource.update(resp["Response"])
        resource["PolicyDocument"] = json.loads(resource["PolicyDocument"])

        # in tencentcloud both "*" and "*:*" mean all resources/services
        # here we only use "*:*"
        for s in resource["PolicyDocument"]["statement"]:
            if "action" in s:
                actions = s["action"]
                if isinstance(actions, str):
                    # to do more: convert to list
                    if actions == "*":
                        s["action"] = ["*:*"]
                    else:
                        s["action"] = [actions]
                if isinstance(actions, list):
                    for idx, act in enumerate(s["action"]):
                        if act == "*":
                            s["action"][idx] = "*:*"


@Policy.filter_registry.register('has-allow-all')
class AllowAllIamPolicies(Filter):
    """AllowAllIamPolicies

    :example:

    .. code-block:: yaml

        policies:
        - name: cam-policy-overly-permissive
          resource: tencentcloud.cam-policy
          filters:
          - type: has-allow-all
    """
    schema = type_schema('has-allow-all')
    permissions = ()

    def has_allow_all_policy(self, resource):
        """has_allow_all_policy"""
        self.manager.get_policy_content(resource)

        for s in resource["PolicyDocument"]["statement"]:
            if "condition" not in s and s["effect"] == "allow":
                if ("action" in s and "*:*" in s["action"] and
                        "resource" in s and
                        (isinstance(s["resource"], str) and s["resource"] == "*" or
                         isinstance(s["resource"], list) and "*" in s["resource"])):
                    return True
        return False

    def process(self, resources, event=None):
        """process"""
        results = [r for r in resources if self.has_allow_all_policy(r)]
        self.log.info(
            "%d of %d cam policies have allow all.",
            len(results), len(resources))
        return results


@Policy.filter_registry.register('check-permissions')
class CheckPermissions(Filter):
    """CheckPermissions

    :example:

    .. code-block:: yaml

        policies:
        - name: cam-policy-check-permissions
          resource: tencentcloud.cam-policy
          filters:
          - type: check-permissions
            match: allowed
            actions:
            - cos:GetBucket
            match-operator: or
    """
    schema = type_schema(
        'check-permissions', **{
            'match': {'oneOf': [
                {'enum': ['allowed', 'denied']},
                {'$ref': '#/definitions/filters/valuekv'},
                {'$ref': '#/definitions/filters/value'}]},
            'match-operator': {'enum': ['and', 'or']},
            'actions': {'type': 'array', 'items': {'type': 'string'}},
            'required': ('actions', 'match')})
    schema_alias = True
    eval_annotation = 'c7n:perm-matches'

    def validate(self):
        """validate"""
        for action in self.data['actions']:
            if ':' not in action[1:-1]:
                raise PolicyValidationError(
                    "invalid check-permissions action: '%s' must be in the form <service>:<action>"
                    % (action,))
        return self

    def get_permissions(self):
        """get_permissions"""
        return ()

    def get_eval_matcher(self):
        """get_eval_matcher"""
        if isinstance(self.data['match'], str):
            if self.data['match'] == 'denied':
                value = 'deny'
            else:
                value = 'allow'
            vf = ValueFilter({'type': 'value', 'key':
                              'effect', 'value': value})
        else:
            vf = ValueFilter(self.data['match'])
        vf.annotate = False
        return vf

    def process(self, resources, event=None):
        """process"""
        actions = set(self.data["actions"])
        matcher = self.get_eval_matcher()
        op = self.data.get("match-operator", "and") == "and" and all or any

        results = []

        for resource in resources:
            self.manager.get_policy_content(resource)
            statements = resource["PolicyDocument"]["statement"]
            matched_statements = []
            matched_flags = []
            for s in statements:
                if (matcher(s) and
                        actions.issubset(s["action"])):
                    # match and actions are both ok
                    matched_statements.append(s)
                    matched_flags.append(True)
                else:
                    matched_flags.append(False)
            if op(matched_flags):
                resource[self.eval_annotation] = matched_statements
                results.append(resource)
        return results


@Policy.filter_registry.register('used')
class UsedIamPolicies(Filter):
    """UsedIamPolicies

    :example:

    .. code-block:: yaml

        policies:
        - name: cam-policy-used
          resource: tencentcloud.cam-policy
          filters:
          - type: used
            state: true
    """
    schema = type_schema('used', state={'type': 'boolean'})
    permissions = ()

    def process(self, resources, event=None):
        """process"""
        results = []
        if self.data.get("state", True):
            for resource in resources:
                if resource["AttachEntityCount"] > 0:
                    results.append(resource)
        else:
            for resource in resources:
                if resource["AttachEntityCount"] == 0:
                    results.append(resource)
        return results
