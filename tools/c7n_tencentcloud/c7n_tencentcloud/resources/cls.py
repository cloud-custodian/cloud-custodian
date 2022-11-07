# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager, DescribeSource
from c7n_tencentcloud.utils import PageMethod


class LogGroupDescribe(DescribeSource):
    def augment(self, resources):
        """
        Resource comes with tags, no need to re-query
        """
        return resources


@resources.register("cls")
class LogTopic(QueryResourceManager):
    """"
    CLS - Cloud Log Service (CLS) is a centralized logging solution
    https://www.tencentcloud.com/document/product/614/11254?lang=en&pg=
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
        metrics_instance_id_name = "uin"  # Namespace=QCE/CLS
        taggable = True

    source_mapping = {'describe': LogGroupDescribe}
