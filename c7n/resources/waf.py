# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import ConfigSource, QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import universal_augment
from c7n.filters import ValueFilter, ListItemFilter
from c7n.utils import type_schema, local_session


class DescribeRegionalWaf(DescribeSource):

    def get_permissions(self):
        perms = super().get_permissions()
        perms.remove('waf-regional:GetWebAcl')
        return perms

    def augment(self, resources):
        resources = super().augment(resources)
        return universal_augment(self.manager, resources)


class DescribeWafV2(DescribeSource):

    def get_permissions(self):
        perms = super().get_permissions()
        perms.remove('wafv2:GetWebAcl')
        return perms

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client(
            'wafv2',
            region_name=self.manager.region
        )

        def _detail(webacl):
            response = client.get_web_acl(
                Name=webacl['Name'],
                Id=webacl['Id'],
                Scope=webacl['Scope']
            )
            detail = response.get('WebACL', {})

            return {**webacl, **detail}

        with_tags = universal_augment(self.manager, resources)

        return list(map(_detail, with_tags))

    # set REGIONAL for Scope as default
    def get_query_params(self, query):
        q = super(DescribeWafV2, self).get_query_params(query)
        if q:
            if 'Scope' not in q:
                q['Scope'] = 'REGIONAL'
        else:
            q = {'Scope': 'REGIONAL'}
        return q

    def resources(self, query):
        scope = (query or {}).get('Scope', 'REGIONAL')
        # The AWS API does not include the scope as part of the WebACL information, but scope
        # is a required parameter for most API calls - we augment the resource with the desired
        # scope here in order to use it downstream for API calls
        return [
            {'Scope': scope, **r}
            for r in super().resources(query)
        ]

    def get_resources(self, ids):
        params = self.get_query_params(None)
        scope = (params or {}).get('Scope', 'REGIONAL')

        resources = self.query.filter(self.manager, **params)
        return [
            {'Scope': scope, **r}
            for r in resources
            if r[self.manager.resource_type.id] in ids
        ]


class DescribeWaf(DescribeSource):

    def get_permissions(self):
        perms = super().get_permissions()
        perms.remove('waf:GetWebAcl')
        return perms


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
        permissions_augment = ('waf:GetWebACL', "waf:ListTagsForResource")
        global_resource = True

    source_mapping = {
        'describe': DescribeWaf,
        'config': ConfigSource
    }


@resources.register('waf-regional')
class RegionalWAF(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "waf-regional"
        enum_spec = ("list_web_acls", "WebACLs", None)
        detail_spec = ("get_web_acl", "WebACLId", "WebACLId", "WebACL")
        name = "Name"
        id = "WebACLId"
        arn = "WebACLArn"
        dimension = "WebACL"
        cfn_type = config_type = "AWS::WAFRegional::WebACL"
        arn_type = "webacl"
        # override defaults to casing issues
        permissions_enum = ('waf-regional:ListWebACLs',)
        permissions_augment = ('waf-regional:GetWebACL', "waf-regional:ListTagsForResource")
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
        arn = "ARN"
        dimension = "WebACL"
        cfn_type = config_type = "AWS::WAFv2::WebACL"
        arn_type = "webacl"
        # override defaults to casing issues
        permissions_enum = ('wafv2:ListWebACLs',)
        permissions_augment = ('wafv2:GetWebACL', "wafv2:ListTagsForResource")
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


@WAFV2.filter_registry.register('web-acl-rules')
class WAFV2ListAllRulesFilter(ListItemFilter):
    """
    Return all rules inside the Web ACL, including rules in rule groups.
    Allows filtering based on any field within the rules data.

    :example:

    .. code-block:: yaml

        policies:
          - name: find-rule-groups
            resource: aws.wafv2
            filters:
              - type: web-acl-rules
                attrs:
                  - type: value
                    key: Type
                    value: RuleGroup
                    op: in

    """

    schema = type_schema(
        'web-acl-rules',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'}
    )
    permissions = (
        'wafv2:GetRuleGroup',
        'wafv2:DescribeManagedRuleGroup',
    )
    annotate_items = True
    item_annotation_key = 'c7n:WebACLAllRules'

    def get_item_values(self, resource):
        client = local_session(self.manager.session_factory).client(
            'wafv2', region_name=self.manager.region
        )

        all_rules = []

        for rule in resource.get('Rules', []):
            statement = rule.get("Statement", {})
            rule_group_ref = statement.get('RuleGroupReferenceStatement')
            managed_group_ref = statement.get('ManagedRuleGroupStatement')

            # Standalone Rules
            if not rule_group_ref and not managed_group_ref:
                all_rules.append({
                    "Type": "Standalone",
                    "Name": rule.get('Name'),
                    "Rules": rule
                })
                continue

            # Customer Managed Rule Groups
            if rule_group_ref:
                arn = rule_group_ref['ARN']
                scope = resource['Scope']
                try:
                    resp = client.get_rule_group(
                        Name=arn.split('/')[-2],
                        Id=arn.split('/')[-1],
                        Scope=scope
                    )
                    rg = resp.get('RuleGroup', {})
                    all_rules.append({
                        "Type": "CustomerRuleGroup",
                        "Name": rule.get('Name'),
                        "RuleGroupARN": arn,
                        "Rules": rg.get('Rules', [])
                    })
                except client.exceptions.WAFNonexistentItemException:
                    all_rules.append({
                        "Type": "UnknownRuleGroup",
                        "Name": rule.get('Name'),
                        "RuleGroupARN": arn,
                        "Error": "Unable to retrieve rule group"
                    })

            # AWS Managed Rule Groups
            elif managed_group_ref:
                try:
                    resp = client.describe_managed_rule_group(
                        VendorName=managed_group_ref['VendorName'],
                        Name=managed_group_ref['Name'],
                        Scope=resource['Scope']
                    )
                    rules_meta = resp.get('Rules', [])
                    all_rules.append({
                        "Type": "ManagedRuleGroup",
                        "Name": rule.get('Name'),
                        "ManagedGroup": managed_group_ref['Name'],
                        "Rules": [{"Name": r['Name'], "Action": r.get('Action', {})} for r in rules_meta]
                    })
                except client.exceptions.WAFNonexistentItemException:
                    all_rules.append({
                        "Type": "ManagedRuleGroup",
                        "Name": rule.get('Name'),
                        "Error": "Unable to describe managed rule group"
                    })

        return all_rules
