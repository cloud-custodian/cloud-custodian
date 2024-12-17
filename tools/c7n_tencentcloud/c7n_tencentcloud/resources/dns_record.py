# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod, isoformat_datetime_str
import pytz


@resources.register("dns-record")
class DnsRecord(QueryResourceManager):
    """dnspod

    Docs on dnspod
    https://www.tencentcloud.com/document/product/1157/53854
    https://www.tencentcloud.com/document/product/1157/51290

    :example:

    .. code-block:: yaml

        policies:

    """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "DomainId"
        endpoint = "dnspod.tencentcloudapi.com"
        service = "dnspod"
        version = "2021-03-23"
        enum_spec = ("DescribeDomainList", "Response.DomainList[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "domain"
        taggable = True

    def augment(self, resources):
        record_resources = []
        cli = self.get_client()
        for resource in resources:
            paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 100}}
            resp = cli.execute_paged_query("DescribeRecordList",
                                           {"Domain": resource["Name"]},
                                           "Response.RecordList[]",
                                           paging_def)
            for item in resp:
                item["domain"] = "{}.{}".format(item["Name"], resource["Name"])
            record_resources += resp
        return record_resources
