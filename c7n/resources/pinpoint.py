# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo


@resources.register('pinpoint-app')
class PinpointApp(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'pinpoint'
        arn_type = 'apps'
        enum_spec = ('get_apps', 'ApplicationsResponse.Item', None)
        name = "Name"
        id = 'Id'
        universal_taggable = True
        cfn_type = 'AWS::Pinpoint::App'
        arn = "Arn"
        permission_prefix = 'mobiletargeting'

    def augment(self, resources):
        for resource in resources:
            tags = resource.get('tags', {})
            formatted_tags = [{'Key': k, 'Value': v} for k, v in tags.items()]
            resource['Tags'] = formatted_tags
        return resources
