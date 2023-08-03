# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


@resources.register("aws.xray-group")
class XRayGroup(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "xray"
        enum_spec = ('get_groups', 'Groups', None)
        arn_type = "group"
        arn = "GroupARN"
        id = "GroupName"
        name = "GroupName"
        cfn_type = "AWS::XRay::Group"
        universal_taggable = object()

    source_mapping = {
       "describe": query.DescribeWithResourceTags,
    }



@resources.register("aws.xray-rule")
class XRaySamplingRule(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "xray"
        enum_spec = ('get_sampling_rules', 'SamplingRuleRecords', None)
        arn_type = "sampling-rule"
        cfn_type = "AWS::XRay::SamplingRule"
        universal_taggable = object()

    source_mapping = {
       "describe": query.DescribeWithResourceTags,
    }
