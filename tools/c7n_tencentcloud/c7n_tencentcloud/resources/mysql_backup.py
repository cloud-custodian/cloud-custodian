# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod, isoformat_datetime_str
import pytz


@resources.register("mysql-backup")
class MySQLBackUp(QueryResourceManager):
    """mysql-backup"""

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "InstanceId"
        endpoint = "cdb.tencentcloudapi.com"
        service = "cdb"
        version = "2017-03-20"
        enum_spec = ("DescribeDBInstances", "Response.Items[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "instanceId"
        taggable = True
        datetime_fields_format = {
            "Date": ("%Y-%m-%d %H:%M:%S", pytz.timezone("Asia/Shanghai"))
        }

    def augment(self, resources):
        backup_resources = []
        cli = self.get_client()
        for resource in resources:
            resp = cli.execute_query("DescribeBackups",
                                     {"InstanceId": resource["InstanceId"]})
            items = resp["Response"]["Items"]
            field_format = self.resource_type.datetime_fields_format["Date"]
            for item in items:
                item["Date"] = isoformat_datetime_str(item["Date"],
                                                      field_format[0],
                                                      field_format[1])
            backup_resources += items
        return backup_resources
