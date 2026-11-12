# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod


@resources.register("cls")
class LogTopic(QueryResourceManager):
    """
    CLS - Cloud Log Service (CLS) is a centralized logging solution
    https://www.tencentcloud.com/document/product/614/11254?lang=en&pg=

    :example:

    .. code-block:: yaml

        policies:
        - name: tencentcloud-cls
          resource: tencentcloud.cls
          filters:
            - or:
              - "Period": 7
              - "Period": 3600
              - "Period": None
    """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "TopicId"
        endpoint = "cls.tencentcloudapi.com"
        service = "cls"
        version = "2020-10-16"
        enum_spec = ("DescribeTopics", "Response.Topics[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "topic"
        taggable = True
        metrics_enabled = True
        metrics_dimension_def = [("uin", "c7n:uin"), ("TopicId", "TopicId")]
        metrics_instance_id_name = "TopicId"
        metrics_namespace = "QCE/CLS"

    def augment(self, resources):
        """
        Resource comes with tags, no need to re-query
        """
        for res in resources:
            res["c7n:uin"] = self.config.account_id
        return resources
