# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod


@resources.register("eip")
class EIP(QueryResourceManager):
    """Elastic IP address

    Docs on EIP resource
    https://www.tencentcloud.com/document/product/215/16702

    :example:

    .. code-block:: yaml

        policies:
        - name: tencentcloud-eip
          resource: tencentcloud.eip
          filters:
            - AddressIp: "43.159.34.197"
    """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "AddressId"
        endpoint = "vpc.tencentcloudapi.com"
        service = "vpc"
        version = "2017-03-12"
        enum_spec = ("DescribeAddresses", "Response.AddressSet[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "eip"
        taggable = True
