# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod, isoformat_datetime_str
from c7n.filters.core import Filter
import pytz
from c7n.utils import type_schema


@resources.register("mysql")
class MySQL(QueryResourceManager):
    """
    mysql: distributed data storage service, relational databases
    https://www.tencentcloud.com/document/product/236/5147

    :example:

    .. code-block:: yaml

        policies:
        - name: test_cdb_engine_value
          resource: tencentcloud.mysql
          filters:
            - type: value
              key: EngineType
              value:
                - InnoDB
                - RocksDB
              op: in
            - type: value
              key: EngineVersion
              op: in
              value:
                - '5.5'
                - '5.6'
                - '5.7'
                - '8.0'
    """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "InstanceId"
        endpoint = "cdb.tencentcloudapi.com"
        service = "cdb"
        version = "2017-03-20"
        enum_spec = ("DescribeDBInstances", "Response.Items[]", {})
        metrics_enabled = True
        metrics_namespace = "QCE/CDB"
        metrics_dimension_def = [("InstanceId", "InstanceId"), ("InstanceType", "InstanceType")]
        metrics_instance_id_name = "InstanceId"

        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "instanceId"
        taggable = True

        datetime_fields_format = {
            "CreateTime": ("%Y-%m-%d %H:%M:%S", pytz.timezone("Asia/Shanghai"))
        }

    def augment(self, resources):
        for resource in resources:
            field_format = self.resource_type.datetime_fields_format["CreateTime"]
            resource["CreateTime"] = isoformat_datetime_str(resource["CreateTime"],
                                                            field_format[0],
                                                            field_format[1])
        return resources


@MySQL.filter_registry.register('encryption')
class EncryptionFilter(Filter):
    """
    :example:

    .. code-block:: yaml

        policies:
        - name: test_cdb_encryption_not_enabled_filter
          resource: tencentcloud.mysql
          filters:
            - type: encryption
              value: 'NO'
    """

    schema = type_schema('encryption', value={'type': 'boolean'})

    def process(self, resources, event=None):
        value = self.data.get('value', True)
        return [r for r in resources if self.encryption_check(r["InstanceId"]) == value]

    def encryption_check(self, instance_id):
        cli = self.manager.get_client()
        resp = cli.execute_query("DescribeDBInstanceInfo", {"InstanceId": instance_id})
        return resp["Response"]["Encryption"] == "YES"
