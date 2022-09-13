# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod


@resources.register("cvm")
class CVM(QueryResourceManager):
    """CVM"""
    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "InstanceId"
        endpoint = "cvm.tencentcloudapi.com"
        service = "cvm"
        version = "2017-03-12"
        enum_spec = ("DescribeInstances", "Response.InstanceSet[]", {})
        metrics_instance_id_name = "InstanceId"
        paging_def = {"method": PageMethod.Offset, "limit": {"Key": "Limit", "value": 20}}
        resource_preifx = "instance"
