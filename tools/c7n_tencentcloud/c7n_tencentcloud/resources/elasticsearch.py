# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod


@resources.register("elasticsearch")
class Elasticsearch(QueryResourceManager):
    """
    elasticsearch - Tencent Cloud Elasticsearch Service (ES) is a cloud-managed Elasticsearch
     service that is highly available and scalable

    https://www.tencentcloud.com/document/product/845/16478?lang=en&pg=

    :example:

    .. code-block:: yaml

        policies:
        - name: tencentcloud-elasticsearch
          resource: tencentcloud.elasticsearch
          filters:
            - type: value
              key: NodeInfoList.NodeType
              op: in
              value:
                - ES.S1.MEDIUM4
    """
    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "InstanceId"
        endpoint = "es.tencentcloudapi.com"
        service = "es"
        version = "2018-04-16"
        enum_spec = ("DescribeInstances", "Response.InstanceList[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "instance"
        taggable = True
        metrics_enabled = True
        metrics_dimension_def = [("InstanceId", "InstanceId")]
        metrics_instance_id_name = "InstanceId"
        metrics_namespace = "QCE/CES"
