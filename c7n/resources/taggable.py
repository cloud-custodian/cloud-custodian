# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""AWS Generic resource to process across all taggable resources."""

from functools import partial

from jsonschema import Draft7Validator as JsonSchemaValidator

from c7n.config import Bag
from c7n.exceptions import PolicyValidationError
from c7n.manager import resources
from c7n import query
from c7n.utils import local_session


def _make_schema_item(props):
    return {"type": "object", "additionalProperties": False, "properties": props}


class DescribeTaggable(query.DescribeSource):

    schema = {
        "type": "array",
        "items": {
            "oneOf": [
                _make_schema_item({"non_compliant": {"type": "boolean"}}),
                _make_schema_item({"non_tagged": {"type": "boolean"}}),
                _make_schema_item(
                    {"resource_types": {"type": "array", "items": {"type": "string"}}}),
                _make_schema_item({
                    "with_tags": {
                        "type": "array", "items": _make_schema_item(
                            {'Key': {'type': 'string'},
                             'Values': {'type': 'array', 'items': {"type": "string"}}}
                        )
                    }
                })
            ]
        }
    }

    def get_params_tagging(self, query):
        params = {}
        if query.get('non_compliant'):
            params['IncludeComplianceDetails'] = True
            params['ExcludeCompliantResources'] = True
        if query.get('resource_types'):
            params['ResourceTypeFilters'] = query.resource_types
        if query.get('with_tags'):
            params['TagFilters'] = query.with_tags
        return params

    def get_params_explorer(self, query):
        parts = [
            f"region:{self.manager.config.region}",
            f"accountid:{self.manager.config.account_id}",
            "tag:none",
            "resourcetype.supports:tags",
        ]

        if query.get('resource_types'):
            for rt in query.resource_types:
                parts.append(f'resourcetype:{rt}')
        params = {'QueryString': " ".join(parts)}
        return params

    def resources(self, query):
        query = Bag(query)
        session = local_session(self.manager.session_factory)
        client = session.client('resourcegroupstaggingapi')
        pager = client.get_paginator('get_resources')

        results = []
        for page in pager.paginate(**self.get_params_tagging(query)):
            results.extend(page.get('ResourceTagMappingList', []))

        tcount = len(results)
        self.manager.log.debug("resourcegrouptagging resources %d" % tcount)
        if not ('with_tags' not in query and 'non_tagged' in query):
            return results

        client = session.client('resource-explorer-2')
        pager = client.get_paginator("search")
        ids = {r['ResourceARN'] for r in results}
        ids = set()
        normalize = partial(self.normalize_explorer_results, query=query)

        for page in pager.paginate(**self.get_params_explorer(query)):
            results.extend(
                [r for r in normalize(page.get("Resources", []))
                 if r['ResourceARN'] not in ids]
            )
        self.manager.log.debug("resource-explorer resources %d" % (len(results) - tcount))
        return results

    def normalize_explorer_results(self, exp2_batch, query=None):
        page = []
        compliance = {}

        if query and query.get('non_compliant'):
            compliance = {'ComplianceStatus': False}
            compliance['MissingTagKeys'] = query.get('check_policy_tags', [])

        for r in exp2_batch:
            e_tags = [p['Data'] for p in r['Properties'] if p['Name'] == 'tags']
            if not e_tags:
                r_tags = []
            else:
                r_tags = e_tags[0]

            page.append(
                dict(
                    ResourceARN=r['Arn'],
                    Tags=r_tags,
                    OwningAccountId=r['OwningAccountId'],
                    ResourceType=r['ResourceType'],
                    LastReportedAt=r['LastReportedAt'],
                    ComplianceDetails=compliance
                )
            )

        return page

    def get_query_params(self, query_params):
        query = dict(query_params or [])
        for item in self.manager.data.get('query'):
            query.update(item)
        return query


@resources.register("taggable")
class Taggable(query.QueryResourceManager):
    """An abstract resource type that represents any taggable resource
    in AWS. Utilizies server side querying wherever possible utilizing
    resource group tagging and resource-explorer-2 apis to provide for
    efficient query of non compliant and non tagged resources, while also
    providing for bulk tagging operations on those resources.

    This primarily utilizes server side queries against these two services
    to effect functionality, as such the functionality is mostly exposed
    via the policy `query` block. Additionally there are pre-requisites on
    the account enablement of those two services, service linked role for
    resource-explorer, and an organizations tag policy for non_compliant
    resource querying active on account, note the tag policy only needs
    to be in reporting mode.

    .. code-block:: yaml

      policies:
         - name: non-compliant
           resource: aws.taggable
           query:
            - non_compliant: true
            - non_tagged: true
            - check_policy_tags: ["Owner"]


    `non_compliant` utilizes the reporting of an applied organization tag
    policy in affect against the account/region to determine resources that
    are non compliant. `check_policy_tags` provides a sanity check of the
    policy authors expectation of the tags being checked, and is verified
    against what's actually in the account.

    `non_tagged` enables the use of resource-explorer to supplement the
    results with resources that have never been tagged. It is safe to run
    against explorer aggregator accounts, as it scopes to only resources
    within an account.

    `resource_types` can be specified as well, to scope to particular
    resources types. notably this resource supports resource types not
    actively supported by custodian, it represents all taggable
    resources within the provider. Note the values here are represented by
    those used by the tagging / resource explorer services.

    See the table here for vocabulary
    https://docs.aws.amazon.com/resource-explorer/latest/userguide/supported-resource-types.html

    `with_tags` represents a server side filter to only return results
    matching resources with a particular set of tags and tag values.


    .. code-block:: yaml

      policies:
         - name: non-compliant
           resource: aws.taggable
           query:
            - resource_types: [ec2:instance, ec2:security-group]
            - with_tags:
               - Key: App
               - Values: [Apple, Orange, Grapefruit]


    The example above will only return ec2 instances and security groups
    with any of the three defined values for the App tag.
    """

    source_mapping = {"describe": DescribeTaggable}

    class resource_type(query.TypeInfo):
        id = 'ResourceARN'
        filter_name = None
        service = 'resourcegrouptagging'
        name = 'ResourceARN'
        arn = name
        permission_prefix = "tag"
        universal_taggable = object()

    def get_permissions(self):
        return ("tag:GetResources", "resource-explorer-2:Search",)

    def validate(self):
        if 'query' not in self.data:
            raise PolicyValidationError(
                "taggable resource requires the use of a `query` block, see docs"
            )
        validator = JsonSchemaValidator(DescribeTaggable.schema)
        errors = list(validator.iter_errors(self.data['query']))
        if errors:
            raise PolicyValidationError(
                "taggable resource query misconfiguration %s" % errors
            )
