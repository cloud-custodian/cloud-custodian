# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import type_schema

from c7n.filters import Filter, ValueFilter

from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod


@resources.register("vpc")
class VPC(QueryResourceManager):
    """
    vpc - Virtual Private Cloud (VPC)
    https://www.tencentcloud.com/document/product/215/535?lang=en&pg=
    """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "VpcId"
        endpoint = "vpc.tencentcloudapi.com"
        service = "vpc"
        version = "2017-03-12"
        enum_spec = ("DescribeVpcs", "Response.VpcSet[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": "20"}}
        resource_prefix = "vpc"
        taggable = True


@VPC.filter_registry.register('flow-logs')
class FlowLogFilter(Filter):
    """
    Are flow logs enabled on the resource.
    Multiple rules only need one match, and the match content needs to match all
    """

    schema = type_schema(
        'flow-logs',
        enabled={'type': 'boolean', 'default': False},
        match={'type': 'array', 'items': {
            'oneOf': [
                {'$ref': '#/definitions/filters/value'},
                {'type': 'object', 'minProperties': 1, 'maxProperties': 1},
            ]}})

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.resource_type = self.manager.get_model()

    def process(self, resources, event=None):
        client = self.manager.get_client()
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        flow_logs = client.execute_paged_query("DescribeFlowLogs", {},
                                               "Response.FlowLog[]",
                                               paging_def)
        enabled = self.data.get('enabled', False)
        matchers = []
        for matcher in self.data.get('match', []):
            vf = ValueFilter(matcher)
            vf.annotate = False
            matchers.append(vf)
        results = []

        resource_map = {}
        for fl in flow_logs:
            resource_map.setdefault(fl['VpcId'], []).append(fl)
        for r in resources:
            logs = resource_map.get(r[self.resource_type.id])
            if logs is None:
                if not enabled:
                    results.append(r)
                continue

            if enabled:
                found = False
                # multiple log rules, using 'or' to match,only one match is needed
                for log in logs:
                    found = True
                    # matchers, using 'and' to match,need to match all
                    for matcher in matchers:
                        if not matcher(log):
                            found = False
                            break
                    if found:
                        break
                if found:
                    results.append(r)

        return results
