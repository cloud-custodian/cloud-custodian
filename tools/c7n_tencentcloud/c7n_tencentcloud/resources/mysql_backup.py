# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod, isoformat_datetime_str
import pytz


@resources.register("mysql-backup")
class MySQLBackUp(QueryResourceManager):
    """mysql-backup

    Docs on mysql-backup
    https://www.tencentcloud.com/document/product/236/37796

    :example:

    .. code-block:: yaml

        policies:
        - name: test_cdb_backup_create_time
          resource: tencentcloud.mysql-backup
          filters:
            - type: value
              key: Date
              value: 1
              value_type: age
              op: greater-than
    """

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
                # backups in non SUCCESS status don't have a proper date yet
                if item["Status"] != "SUCCESS":
                    continue
                item["Date"] = isoformat_datetime_str(item["Date"],
                                                      field_format[0],
                                                      field_format[1])
            backup_resources += items
        return backup_resources
