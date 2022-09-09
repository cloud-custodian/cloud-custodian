# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager


@resources.register("cvm")
class CVM(QueryResourceManager):
    """CVM"""
    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "InstanceId"
        endpoint = "cvm.tencentcloudapi.com"
        service = "cvm"
        version = "2017-03-12"
        enum_spec = ("DescribeInstances", "Response.InstanceSet[]", None)
        resource_preifx = "instance"
