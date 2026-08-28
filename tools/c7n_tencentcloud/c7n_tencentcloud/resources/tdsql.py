# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod, isoformat_datetime_str
import pytz


@resources.register("tdsql")
class TDSQL(QueryResourceManager):
    """
        TDSQL for MySQL: TDSQL for MySQL is a distributed database service
        deployed in Tencent Cloud that supports automatic sharding (horizontal splitting)
        and the Shared Nothing architecture.
        https://www.tencentcloud.com/document/product/1042/33311

        :example:

        .. code-block:: yaml

            policies:
            - name: check-tdsql
              resource: tencentcloud.tdsql
              filters:
                - type: value
                  key: InstanceId
                  value: tdsqlshard-123456
        """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "InstanceId"
        endpoint = "dcdb.tencentcloudapi.com"
        service = "dcdb"
        version = "2018-04-11"
        enum_spec = ("DescribeDCDBInstances", "Response.Instances[]", {})
        metrics_enabled = True
        metrics_namespace = "QCE/DCDB"
        metrics_dimension_def = [("InstanceId", "InstanceId"), ("InstanceType", "InstanceType")]
        metrics_instance_id_name = "InstanceId"

        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 10}}
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
