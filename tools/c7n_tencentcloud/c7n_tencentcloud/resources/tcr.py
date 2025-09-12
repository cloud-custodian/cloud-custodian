# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.filters import Filter, ValueFilter
from c7n.utils import type_schema
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod


@resources.register("tcr")
class TCR(QueryResourceManager):
    """
    TCR - Tencent Container Registry (TCR) is a container image cloud hosting service
    https://www.tencentcloud.com/document/product/614/11254?lang=en&pg=
    """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "RegistryId"
        endpoint = "tcr.tencentcloudapi.com"
        service = "tcr"
        version = "2019-09-24"
        enum_spec = ("DescribeInstances", "Response.Registries[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "instance"
        taggable = True


@TCR.filter_registry.register('lifecycle-rule')
class LifecycleRule(Filter):
    """
    Lifecycle rule filtering
    Multiple rules only need one match, and the match content needs to match all

    :example:

    .. code-block:: yaml

        policies:
          - name: tcr-no-lifecycle
            resource: tencentcloud.tcr
            filters:
              - type: lifecycle-rule
                state: true
                match:
                  - NamespaceName: custodian-test-namespace-2

    """
    schema = type_schema(
        'lifecycle-rule',
        state={'type': 'boolean'},
        match={'type': 'array', 'items': {
            'oneOf': [
                {'$ref': '#/definitions/filters/value'},
                {'type': 'object', 'minProperties': 1, 'maxProperties': 1},
            ]}})

    def process(self, resources, event=None):
        client = self.manager.get_client()

        state = self.data.get('state', False)
        matchers = []
        for matcher in self.data.get('match', []):
            vf = ValueFilter(matcher)
            vf.annotate = False
            matchers.append(vf)
        results = []

        for r in resources:
            paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
            policys = client.execute_paged_query("DescribeTagRetentionRules",
                                                 {"RegistryId": r[self.manager.resource_type.id]},
                                                 "Response.RetentionPolicyList[]",
                                                 paging_def)
            found = False
            # multiple log rules, using 'or' to match,only one match is needed
            for policy in policys:
                found = True
                # matchers, using 'and' to match,need to match all
                for match in matchers:
                    if not match(policy):
                        found = False
                        break
                if found:
                    break

            if found and state:
                results.append(r)
            elif not found and not state:
                results.append(r)

        return results
