# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import ConfigSource, QueryResourceManager, TypeInfo, DescribeSource, ResourceQuery
from c7n.tags import universal_augment
from c7n.filters import ValueFilter, ListItemFilter
from c7n.utils import type_schema, local_session
from c7n.actions import BaseAction
from c7n.exceptions import PolicyValidationError
from c7n.resources.aws import shape_validate


class DescribeRegionalWaf(DescribeSource):
    def get_permissions(self):
        perms = super().get_permissions()
        perms.remove('waf-regional:GetWebAcl')
        return perms

    def augment(self, resources):
        resources = super().augment(resources)
        return universal_augment(self.manager, resources)


class WafV2ResourceQuery(ResourceQuery):
    """Custom query handler that uses us-east-1 for CLOUDFRONT scope WebACLs"""

    def filter(self, resource_manager, **params):
        """Query a set of resources, using us-east-1 for CLOUDFRONT scope."""
        m = self.resolve(resource_manager.resource_type)

        # CloudFront WebACLs must be queried from us-east-1
        region = resource_manager.config.region
        if params.get('Scope') == 'CLOUDFRONT':
            region = 'us-east-1'

        if resource_manager.get_client:
            client = resource_manager.get_client()
        else:
            client = local_session(self.session_factory).client(m.service, region)

        enum_op, path, extra_args = m.enum_spec
        if extra_args:
            params = {**extra_args, **params}
        return (
            self._invoke_client_enum(
                client, enum_op, params, path, getattr(resource_manager, 'retry', None)
            )
            or []
        )


class DescribeWafV2(DescribeSource):
    resource_query_factory = WafV2ResourceQuery

    def get_permissions(self):
        perms = super().get_permissions()
        perms.remove('wafv2:GetWebAcl')
        return perms

    def augment(self, resources):
        # CloudFront WebACLs (Scope=CLOUDFRONT) must be queried from us-east-1
        region = self.manager.region
        if resources and resources[0].get('Scope') == 'CLOUDFRONT':
            region = 'us-east-1'

        client = local_session(self.manager.session_factory).client('wafv2', region_name=region)

        def _detail(webacl):
            response = client.get_web_acl(
                Name=webacl['Name'], Id=webacl['Id'], Scope=webacl['Scope']
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
        return [{'Scope': scope, **r} for r in super().resources(query)]

    def get_resources(self, ids):
        params = self.get_query_params(None)
        scope = (params or {}).get('Scope', 'REGIONAL')

        resources = self.query.filter(self.manager, **params)
        return [{'Scope': scope, **r} for r in resources if r[self.manager.resource_type.id] in ids]


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

    source_mapping = {'describe': DescribeWaf, 'config': ConfigSource}


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

    source_mapping = {'describe': DescribeRegionalWaf, 'config': ConfigSource}


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

    source_mapping = {'describe': DescribeWafV2, 'config': ConfigSource}


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
    permissions = ('wafv2:GetLoggingConfiguration',)
    annotation_key = 'c7n:WafV2LoggingConfiguration'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client(
            'wafv2', region_name=self.manager.region
        )
        logging_confs = client.list_logging_configurations(Scope='REGIONAL')[
            'LoggingConfigurations'
        ]
        resource_map = {r['ARN']: r for r in resources}
        for lc in logging_confs:
            if lc['ResourceArn'] in resource_map:
                resource_map[lc['ResourceArn']][self.annotation_key] = lc

        resources = list(resource_map.values())

        return [r for r in resources if self.match(r.get(self.annotation_key, {}))]


@WAFV2.action_registry.register('set-logging')
class WAFV2SetLogging(BaseAction):
    """
    Action to enable logging for a WAFv2 Web ACL with optional attributes.

    :example:

    .. code-block:: yaml

        policies:
          - name: enable-wafv2-logging
            resource: aws.wafv2
            filters:
              - type: value
                key: Name
                value: my-web-acl
            actions:
              - type: set-logging
                destination: "arn:aws:s3:::aws-waf-logs-bucket"

          - name: enable-wafv2-logging-with-redacted-fields
            resource: aws.wafv2
            filters:
              - type: value
                key: Name
                value: my-web-acl
            actions:
              - type: set-logging
                destination: "arn:aws:s3:::aws-waf-logs-bucket"
                attributes:
                  RedactedFields:
                    - SingleHeader:
                        Name: user-agent
                    - Method: {}
    """

    schema = type_schema(
        'set-logging',
        required=['destination'],
        destination={'type': 'string'},
        attributes={'type': 'object'})

    permissions = ('wafv2:PutLoggingConfiguration',)

    def validate(self):
        destination = self.data['destination']
        if ':' in destination:
            arn_parts = destination.split(':')
            if len(arn_parts) >= 6:
                resource_part = arn_parts[-1]
                if '/' in resource_part:
                    resource_name = resource_part.split('/')[-1]
                else:
                    resource_name = resource_part
                if not resource_name.startswith('aws-waf-logs'):
                    raise PolicyValidationError(
                        f"Destination resource must start with aws-waf-logs, got {resource_name}"
                    )

        # Validate attributes against AWS API schema
        if 'attributes' in self.data:
            cfg = {
                'LoggingConfiguration': {
                    'ResourceArn': 'arn:aws:wafv2:us-east-1:644160558196:regional/webacl/tester/1',
                    'LogDestinationConfigs': [destination]
                }
            }
            cfg['LoggingConfiguration'].update(self.data['attributes'])
            shape_validate(
                cfg, 'PutLoggingConfigurationRequest', 'wafv2'
            )
        return self

    def process(self, resources):
        client = local_session(self.manager.session_factory).client(
            'wafv2', region_name=self.manager.region
        )
        destination = self.data['destination']
        attributes = self.data.get('attributes', {})

        for r in resources:
            resource_arn = r['ARN']
            logging_config = {
                'ResourceArn': resource_arn,
                'LogDestinationConfigs': [destination]
            }
            logging_config.update(attributes)

            self.manager.retry(
                client.put_logging_configuration,
                LoggingConfiguration=logging_config,
                ignore_err_codes=('WAFNonexistentItemException',),
            )
            attrs_info = f" with attributes: {list(attributes.keys())}" if attributes else ""
            self.log.info(
                f"Enabled logging for WAFv2 WebACL {r['Name']} to {destination}{attrs_info}")


@WAFV2.filter_registry.register('web-acl-rules')
class WAFV2ListAllRulesFilter(ListItemFilter):
    """
    Return all rules inside the Web ACL, including rules in rule groups (customer and managed).
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
        'web-acl-rules', attrs={'$ref': '#/definitions/filters_common/list_item_attrs'}
    )
    permissions = (
        'wafv2:GetRuleGroup',
        'wafv2:DescribeManagedRuleGroup',
    )
    annotate_items = True
    item_annotation_key = 'c7n:WebACLAllRules'

    def handle_rule_group_cache(self, client, rule_groups):

        rgcache = {}
        cache = self.manager._cache

        with cache:
            for rg_info in rule_groups:
                arn = rg_info['arn']
                scope = rg_info['scope']
                cache_key = {
                    'region': self.manager.config.region,
                    'account_id': self.manager.config.account_id,
                    'wafv2-rule-group': f"{arn}:{scope}"
                }

                rg_values = cache.get(cache_key)
                if rg_values is not None:
                    rgcache[f"{arn}:{scope}"] = rg_values
                    continue

                resp = client.get_rule_group(
                    Name=arn.split('/')[-2],
                    Id=arn.split('/')[-1],
                    Scope=scope
                )
                rgcache[f"{arn}:{scope}"] = resp.get('RuleGroup', {})
                cache.save(cache_key, rgcache[f"{arn}:{scope}"])

        return rgcache

    def handle_managed_rule_group_cache(self, client, managed_groups):

        mgcache = {}
        cache = self.manager._cache

        with cache:
            for mg_info in managed_groups:
                vendor = mg_info['vendor']
                name = mg_info['name']
                scope = mg_info['scope']
                cache_key = {
                    'region': self.manager.config.region,
                    'account_id': self.manager.config.account_id,
                    'wafv2-managed-group': f"{vendor}:{name}:{scope}"
                }

                mg_values = cache.get(cache_key)
                if mg_values is not None:
                    mgcache[f"{vendor}:{name}:{scope}"] = mg_values
                    continue

                resp = client.describe_managed_rule_group(
                    VendorName=vendor,
                    Name=name,
                    Scope=scope
                )
                mgcache[f"{vendor}:{name}:{scope}"] = resp.get('Rules', [])
                cache.save(cache_key, mgcache[f"{vendor}:{name}:{scope}"])

        return mgcache

    def get_item_values(self, resource):
        client = local_session(self.manager.session_factory).client(
            'wafv2', region_name=self.manager.region
        )

        rule_groups = []
        managed_groups = []

        for rule in resource.get('Rules', []):
            statement = rule.get("Statement", {})
            rule_group_ref = statement.get('RuleGroupReferenceStatement')
            managed_group_ref = statement.get('ManagedRuleGroupStatement')

            if rule_group_ref:
                rule_groups.append({
                    'arn': rule_group_ref['ARN'],
                    'scope': resource['Scope'],
                    'rule': rule
                })
            elif managed_group_ref:
                managed_groups.append({
                    'vendor': managed_group_ref['VendorName'],
                    'name': managed_group_ref['Name'],
                    'scope': resource['Scope'],
                    'rule': rule
                })

        rule_group_cache = {}
        if rule_groups:
            rule_group_cache = self.handle_rule_group_cache(client, rule_groups)

        managed_group_cache = {}
        if managed_groups:
            managed_group_cache = self.handle_managed_rule_group_cache(client, managed_groups)

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

            # Customer Managed Rule Groups Caching
            if rule_group_ref:
                arn = rule_group_ref['ARN']
                scope = resource['Scope']
                cache_key = f"{arn}:{scope}"

                rg = rule_group_cache.get(cache_key, {})
                all_rules.append({
                    "Type": "CustomerRuleGroup",
                    "Name": rule.get('Name'),
                    "RuleGroupARN": arn,
                    "Rules": rg.get('Rules', [])
                })

            # AWS Managed Rule Groups Caching
            elif managed_group_ref:
                vendor = managed_group_ref['VendorName']
                name = managed_group_ref['Name']
                scope = resource['Scope']
                cache_key = f"{vendor}:{name}:{scope}"

                rules_meta = managed_group_cache.get(cache_key, [])
                all_rules.append({
                    "Type": "ManagedRuleGroup",
                    "Name": rule.get('Name'),
                    "ManagedGroup": name,
                    "Rules": [{"Name": r['Name'], "Action": r.get('Action', {})}
                                for r in rules_meta]
                })

        return all_rules
