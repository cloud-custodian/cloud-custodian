# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import ConfigSource, QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import universal_augment
from c7n.filters import ValueFilter
from c7n.utils import type_schema, local_session


class DescribeRegionalWaf(DescribeSource):
    def augment(self, resources):
        resources = super().augment(resources)
        return universal_augment(self.manager, resources)


class DescribeWafV2(DescribeSource):
    def augment(self, resources):
        return universal_augment(self.manager, resources)

    # set REGIONAL for Scope as default
    def get_query_params(self, query):
        q = super(DescribeWafV2, self).get_query_params(query)
        if q:
            if 'Scope' not in q:
                q['Scope'] = 'REGIONAL'
        else:
            q = {'Scope': 'REGIONAL'}
        return q

    def get_resources(self, ids):
        resources = self.query.filter(self.manager, **self.get_query_params(None))
        return [r for r in resources if r[self.manager.resource_type.id] in ids]


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


@resources.register('wafv2')
class WAFV2(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "wafv2"
        enum_spec = ("list_web_acls", "WebACLs", None)
        detail_spec = ("get_web_acl", "Id", "Id", "WebACL")
        name = "Name"
        id = "Id"
        dimension = "WebACL"
        cfn_type = config_type = "AWS::WAFv2::WebACL"
        arn_type = "webacl"
        # override defaults to casing issues
        permissions_enum = ('wafv2:ListWebACLs',)
        permissions_augment = ('wafv2:GetWebACL',)
        universal_taggable = object()

    source_mapping = {
        'describe': DescribeWafV2,
        'config': ConfigSource
    }


@WAFV2.filter_registry.register('logging')
class WAFV2LoggingFilter(ValueFilter):
    """
    Filter by wafv2 logging configuration

    :example:

    .. code-block:: yaml

        policies:
          - name: wafv2-logging-enabled
            resource: aws.wafv2
            filters:
              - not:
                  - type: logging
                    key: ResourceArn
                    value: present

          - name: check-redacted-fields
            resource: aws.wafv2
            filters:
              - type: logging
                key: RedactedFields[].SingleHeader.Name
                value: user-agent
                op: in
                value_type: swap
    """

    schema = type_schema('logging', rinherit=ValueFilter.schema)
    permissions = ('wafv2:GetLoggingConfiguration', )
    annotation_key = 'c7n:WafV2LoggingConfiguration'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client(
            'wafv2', region_name=self.manager.region)
        logging_confs = client.list_logging_configurations(
            Scope='REGIONAL')['LoggingConfigurations']
        resource_map = {r['ARN']: r for r in resources}
        for lc in logging_confs:
            if lc['ResourceArn'] in resource_map:
                resource_map[lc['ResourceArn']][self.annotation_key] = lc

        resources = list(resource_map.values())

        return [
            r for r in resources if self.match(
                r.get(self.annotation_key, {}))]
