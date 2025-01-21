# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod


@resources.register("subnet")
class Subnet(QueryResourceManager):
    """
    subnet - A Virtual Private Cloud consists of at least one subnet.
    Docs on subnet resource
    https://www.tencentcloud.com/document/product/215/535?lang=en&pg=

    :example:

    .. code-block:: yaml

        policies:
        -   name: tencentcloud-subnet
            resource: tencentcloud.subnet
            filters:
            - SubnetId: "subnet-******"
    """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "SubnetId"
        endpoint = "vpc.tencentcloudapi.com"
        service = "vpc"
        version = "2017-03-12"
        enum_spec = ("DescribeSubnets", "Response.SubnetSet[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": "20"}}
        resource_prefix = "subnet"
        taggable = True
