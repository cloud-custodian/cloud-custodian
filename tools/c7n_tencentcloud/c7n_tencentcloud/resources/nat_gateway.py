# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytz
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod, isoformat_datetime_str


@resources.register("nat-gateway")
class NatGateway(QueryResourceManager):
    """nat-gateway"""

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "NatGatewayId"
        endpoint = "vpc.tencentcloudapi.com"
        service = "vpc"
        version = "2017-03-12"
        enum_spec = ("DescribeNatGateways", "Response.NatGatewaySet[]", {})
        metrics_instance_id_name = "NatGatewayId"
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "nat"
        taggable = True
        datetime_fields_format = {
            "CreatedTime": ("%Y-%m-%d %H:%M:%S", pytz.timezone("Asia/Shanghai"))
        }

    def augment(self, resources):
        for resource in resources:
            field_format = self.resource_type.datetime_fields_format["CreatedTime"]
            resource["CreatedTime"] = isoformat_datetime_str(resource["CreatedTime"],
                                                             field_format[0],
                                                             field_format[1])
        return resources
