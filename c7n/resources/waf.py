# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import functools

from c7n.manager import resources
from c7n.query import ConfigSource, QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import universal_augment
from c7n.filters import ValueFilter, ListItemFilter
from c7n.utils import type_schema, local_session
from c7n.actions import BaseAction
from c7n.exceptions import ClientError, PolicyValidationError
from c7n.resources.aws import shape_validate
from c7n.utils import is_not_found


class DescribeRegionalWaf(DescribeSource):
    def get_permissions(self):
        perms = super().get_permissions()
        perms.remove('waf-regional:GetWebAcl')
        return perms

    def augment(self, resources):
        resources = super().augment(resources)
        return universal_augment(self.manager, resources)


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


class DescribeWafV2(DescribeSource):

    # Essentially a copy of DescribeSource.augment with the addition of Scope and Name parameters
    def augment(self, resources):
        client = self.manager.get_client()
        scope = self.manager.scope
        detail_op, param_name, param_key, detail_path = self.manager.resource_type.detail_spec

        op = getattr(client, detail_op)
        if self.manager.retry:
            op = functools.partial(self.manager.retry, op)

        def get_detail(r):
            kwargs = {
                param_name: r[param_key],
                'Scope': scope,
                'Name': r['Name']
            }
            try:
                response = op(**kwargs)
            except ClientError as e:
                if not is_not_found(e):
                    raise
                self.manager.log.warning("Resource not found: %s id:%s" % (detail_op, r[param_key]))
                return None
            r.update(response.get(detail_path, {}))
            r['Scope'] = scope
            return r

        resources = universal_augment(self.manager, resources)
        return [r for r in map(get_detail, resources) if r is not None]

    def get_resources(self, ids):
        params = {'Scope': self.manager.scope}
        resources = self.query.filter(self.manager, **params)
        id_key = self.manager.resource_type.id
        return [r for r in resources if r[id_key] in ids]

    def get_permissions(self):
        perms = super().get_permissions()
        perms.remove('wafv2:GetWebAcl')
        return perms

    # set REGIONAL for Scope as default
    def get_query_params(self, query_params):
        query_params = query_params or {}
        # Parse query from policy data
        queries = self.manager.data.get('query', [])
        for q in queries:
            query_params.update(q)
        query_params['Scope'] = self.manager.scope
        return query_params


@resources.register('wafv2')
class WAFV2(QueryResourceManager):
    """WAFv2 Web ACLs.

    By default, queries REGIONAL scope Web ACLs. To query CloudFront (global)
    Web ACLs, set the scope in the query block:

    .. code-block:: yaml

        policies:
          - name: cloudfront-webacls
            resource: aws.wafv2
            query:
              - Scope: CLOUDFRONT

    CLOUDFRONT-scoped Web ACLs are global resources managed via us-east-1
    regardless of the policy's configured region.
    """

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

    # global_resource is required for universal tagging api calls. In order to have scope-aware
    # global_resource behavior, we need to create a new resource_type instance for each manager
    # to avoid modifying the shared class-level resource_type
    def __init__(self, ctx, data):
        super().__init__(ctx, data)
        self.resource_type = type(
            'WAFV2ResourceType',
            (self.__class__.resource_type,),
            {'global_resource': self.scope == 'CLOUDFRONT'}
        )

    @property
    def scope(self):
        for q in self.data.get('query', []):
            if 'Scope' in q:
                return q['Scope']
        return 'REGIONAL'

    @property
    def scope_region(self):
        """Region to use for wafv2 API calls given a WebACL's Scope.

        CLOUDFRONT WebACLs are global resources addressed via us-east-1; all other
        (REGIONAL) WebACLs use the policy's region.
        """
        return 'us-east-1' if self.scope == 'CLOUDFRONT' else self.region

    def get_client(self):
        return local_session(self.session_factory).client(
            self.resource_type.service, region_name=self.scope_region)


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
        client = self.manager.get_client()
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
        client = self.manager.get_client()
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

            self.log.info(f"Enabled logging for WAFv2 WebACL {r['Name']} to {destination}")


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
        client = self.manager.get_client()

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
