# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

from retrying import RetryError
from tencentcloud.common.exception import TencentCloudSDKException

from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n.utils import type_schema
from c7n_tencentcloud.actions import TencentCloudBaseAction
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod


@resources.register("cbs")
class CBS(QueryResourceManager):
    """CBS"""

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "DiskId"
        endpoint = "cbs.tencentcloudapi.com"
        service = "cbs"
        version = "2017-03-12"
        enum_spec = ("DescribeDisks", "Response.DiskSet[]", {})
        metrics_instance_id_name = "DiskId"
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "instance"
        taggable = True


@CBS.action_registry.register('copy-instance-tags')
class CbsCopyInstanceTagsAction(TencentCloudBaseAction):
    schema_alias = True
    schema = type_schema("copy-instance-tags",
                         tags={"type": "array"})

    t_api_method_name = "ModifyResourceTags"

    def validate(self):
        """validate"""
        if not self.data.get('tags'):
            raise PolicyValidationError("Must specify tags")
        return self

    def _get_tag_request_params(self, resource, instances_tags):
        """
        get cbs tag request params,single resource operation
        https://cloud.tencent.com/document/api/651/35322
        """
        params = {"Resource": self.manager.source.get_resource_qcs([resource])[0],
                  "ReplaceTags": []}
        tags = instances_tags.get(resource["InstanceId"])
        for tag in tags:
            if tag["TagKey"] in self.data.get('tags'):
                params["ReplaceTags"].append(tag)
        return params

    def process(self, resources):
        """
        process copy instance tags
        """
        try:
            client = self.get_tag_client()
            instances_tags = self.get_instances_tag(resources)
            for res in resources:
                params = self._get_tag_request_params(res, instances_tags)
                if len(params["ReplaceTags"]) > 0:
                    resp = client.execute_query(self.t_api_method_name, params)
                    self.log.debug("%s , params: %s,resp: %s ", self.data.get('type'),
                                   json.dumps(params), json.dumps(resp))
        except (RetryError, TencentCloudSDKException) as err:
            raise PolicyExecutionError(err) from err

    def get_instances_tag(self, resources):
        """
        get instances tag
        """
        dict_tag: dir = {}
        qcs = self.manager.get_resource_manager('tencentcloud.cvm').get_qcs_for_cbs(resources)
        tags = self.manager.source.query_helper.get_resource_tags(self.manager.config.region, qcs)
        for tag in tags:
            dict_tag.update({tag["Resource"].split('/')[-1]: tag["Tags"]})
        return dict_tag
