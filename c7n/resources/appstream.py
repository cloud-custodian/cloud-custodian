# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


@resources.register("appstream-fleet")
class AppStreamFleet(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "appstream"
        enum_spec = ('describe_fleets', 'Fleets', None)
        arn_type = "fleet"
        arn = "Arn"
        id = "Name"
        name = "Name"
        config_type = cfn_type = "AWS::AppStream::Fleet"
        universal_taggable = object()
        permissions_augment = ("appstream:ListTagsForResource",)
    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }


@resources.register("appstream-stack")
class AppStreamStack(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "appstream"
        enum_spec = ('describe_stacks', 'Stacks', None)
        arn_type = "stack"
        arn = "Arn"
        id = "Name"
        name = "Name"
        config_type = cfn_type = "AWS::AppStream::Stack"
        universal_taggable = object()

    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }
