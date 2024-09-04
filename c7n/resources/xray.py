# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


@resources.register("xray-group")
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
        permissions_augment = ("xray:ListTagsForResource",)

    source_mapping = {
        "describe": query.DescribeWithResourceTags,
    }


class DescribeRule(query.DescribeWithResourceTags):

    def augment(self, resources):
        for r in resources:
            r.update(r.pop('SamplingRule'))
        return super().augment(resources)


@resources.register("xray-rule")
class XRaySamplingRule(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "xray"
        enum_spec = ('get_sampling_rules', 'SamplingRuleRecords', None)
        arn_type = "sampling-rule"
        arn = "RuleARN"
        cfn_type = "AWS::XRay::SamplingRule"
        universal_taggable = object()
        name = id = "RuleName"

    source_mapping = {
        "describe": DescribeRule
    }
