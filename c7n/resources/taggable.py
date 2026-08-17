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


class DescribeTaggable(query.DescribeSource):

    schema = {
        "non_compliant": {"type": "boolean"},
        "non_tagged": {"type": "boolean"},
        "resource_types": {"type": "array", "items": {"type": "string"}},
        "with_tags": {
            "type": "array", "items": {
                "type": "object",
                "properties": {'Key': {'type': 'string'},
                               'Values': {'type': 'array', 'items': {"type": "string"}}}
            }
        },
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
    """ """

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
        validator = JsonSchemaValidator(DescribeTaggable.schema)
        errors = list(validator.iter_errors(self.data['query']))
        if errors:
            raise PolicyValidationError(
                "taggable resource query misconfiguration %s" % errors
            )
