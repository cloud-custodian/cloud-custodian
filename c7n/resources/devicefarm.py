# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


@resources.register("devicefarm-project")
class DevicefarmProject(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "devicefarm"
        enum_spec = ('list_projects', 'projects', None)
        arn_type = "project"
        arn = "arn"
        id = "arn"
        name = "name"
        config_type = "AWS::DeviceFarm::Project"
        universal_taggable = object()
        permissions_augment = ("devicefarm:ListTagsForResource",)

    source_mapping = {"describe": query.DescribeWithResourceTags, "config": query.ConfigSource}
