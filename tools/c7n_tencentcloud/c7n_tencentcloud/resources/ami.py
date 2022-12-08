# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import itertools

from c7n.utils import type_schema
from c7n.filters import Filter
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod


@resources.register("ami")
class AMI(QueryResourceManager):
    """ami Tencent Cloud image

    Docs on ami resource
    https://www.tencentcloud.com/document/product/213/4940

    :example:

    .. code-block:: yaml

        policies:
        - name: ami_old_and_not_used
          resource: tencentcloud.ami
          filters:
            - type: unused
              value: true
            - type: value
              key: CreatedTime
              value_type: age
              value: 90
              op: greater-than
    """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "ImageId"
        endpoint = "cvm.tencentcloudapi.com"
        service = "cvm"
        version = "2017-03-12"
        enum_spec = ("DescribeImages", "Response.ImageSet[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "instance"
        taggable = True

    def get_resource_query_params(self):
        """
        https://cloud.tencent.com/document/api/213/15715
        only query image-type = PRIVATE_IMAGE
        """
        config_query = self.data.get("query", [])
        params = {
            "Filters": [
                {
                    "Name": "image-type",
                    "Values": ["PRIVATE_IMAGE"]
                }
            ]
        }
        for it in config_query:
            params.update(it)

        return params


@AMI.filter_registry.register('unused')
class ImageUnusedFilter(Filter):
    """Filters images based on usage

    true: image has no instances spawned from it
    false: image has instances spawned from it

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-unused
                resource: tencentcloud.ami
                filters:
                  - type: unused
                    value: true
    """
    schema = type_schema('unused', value={'type': 'boolean'})

    def get_permissions(self):
        return list(itertools.chain(*[
            self.manager.get_resource_manager(m).get_permissions()
            for m in ('ami', 'cvm')]))

    def _pull_cvm_images(self):
        cvm_manager = self.manager.get_resource_manager('cvm')
        return {i['ImageId'] for i in cvm_manager.resources()}

    def process(self, resources, event=None):
        images = self._pull_cvm_images()
        # https://cloud.tencent.com/document/api/213/15753
        # TODO Need to confirm if ImageState is marked as available,to be optimized
        # ImageState
        if self.data.get('value', True):
            return [r for r in resources if r['ImageId'] not in images]
        return [r for r in resources if r['ImageId'] in images]
