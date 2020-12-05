# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import ConfigSource, QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import universal_augment


class DescribeRegionalWaf(DescribeSource):
    def augment(self, resources):
        return universal_augment(self.manager, resources)


@resources.register('waf')
class WAF(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "waf"
        enum_spec = ("list_web_acls", "WebACLs", None)
        detail_spec = ("get_web_acl", "WebACLId", "WebACLId", "WebACL")
        name = "Name"
        id = "WebACLId"
        dimension = "WebACL"
        cfn_type = config_type = "AWS::WAF::WebACL"
        arn_type = "webacl"
        # override defaults to casing issues
        permissions_enum = ('waf:ListWebACLs',)
        permissions_augment = ('waf:GetWebACL',)


@resources.register('waf-regional')
class RegionalWAF(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "waf-regional"
        enum_spec = ("list_web_acls", "WebACLs", None)
        detail_spec = ("get_web_acl", "WebACLId", "WebACLId", "WebACL")
        name = "Name"
        id = "WebACLId"
        dimension = "WebACL"
        cfn_type = config_type = "AWS::WAFRegional::WebACL"
        arn_type = "webacl"
        # override defaults to casing issues
        permissions_enum = ('waf-regional:ListWebACLs',)
        permissions_augment = ('waf-regional:GetWebACL',)
        universal_taggable = object()

    source_mapping = {
        'describe': DescribeRegionalWaf,
        'config': ConfigSource
    }
