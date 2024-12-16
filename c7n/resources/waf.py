# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import ConfigSource, QueryResourceManager, TypeInfo, DescribeSource
from c7n.tags import universal_augment
from c7n.filters import ValueFilter
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


@WAFV2.action_registry.register('enable-logging')
class EnableWAFV2Logging(BaseAction):
    """
    Action to enable logging for WAF WebACLs with S3 Destination

    :example:

    .. code-block:: yaml

    policies:
      - name: enable-wafv2-logging
        resource: aws.wafv2
        actions:
          - type: enable-logging
            log_destination_arn: arn:aws:s3:::logging-destination-bucket
            redacted_fields:
              - type: SingleHeader
                data: authorization
              - type: JsonBody
                match_pattern:
                  All: {}
                match_scope: ALL
                oversize_handling: CONTINUE
            logging_filter:
              Filters:
                - Behavior: KEEP
                  Requirement: MEETS_ALL
                  Conditions:
                    - ActionCondition:
                        Action: ALLOW
                    - LabelNameCondition:
                        LabelName: example-label
              DefaultBehavior: DROP
            managed_by_firewall_manager: true
            log_type: WAF_LOGS
            log_scope: CUSTOMER


    """
    schema = type_schema(
        'enable-logging',
        log_destination_arn={'type': 'string'},
        redacted_fields={
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'type': {'type': 'string', 'enum': [
                        'SingleHeader', 'SingleQueryArgument', 'AllQueryArguments',
                        'UriPath', 'QueryString', 'Body', 'Method', 'JsonBody',
                        'Headers', 'Cookies', 'HeaderOrder', 'JA3Fingerprint']},
                    'data': {'type': 'string'},
                    'oversize_handling': {
                        'type': 'string',
                        'enum': ['CONTINUE', 'MATCH', 'NO_MATCH']
                    },
                    'match_pattern': {'type': 'object'},
                    'match_scope': {'type': 'string', 'enum': ['ALL', 'KEY', 'VALUE']},
                    'invalid_fallback_behavior':
                        {
                            'type': 'string',
                            'enum': ['MATCH', 'NO_MATCH', 'EVALUATE_AS_STRING']
                        },
                    'fallback_behavior': {'type': 'string', 'enum': ['MATCH', 'NO_MATCH']}
                }
            }
        },
        logging_filter={
            'type': 'object',
            'properties': {
                'Filters': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'Behavior': {'type': 'string', 'enum': ['KEEP', 'DROP']},
                            'Requirement': {'type': 'string', 'enum': ['MEETS_ALL', 'MEETS_ANY']},
                            'Conditions': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'ActionCondition': {
                                            'type': 'object',
                                            'properties': {
                                                'Action': {'type': 'string', 'enum': [
                                                    'ALLOW', 'BLOCK', 'COUNT', 'CAPTCHA',
                                                    'CHALLENGE', 'EXCLUDED_AS_COUNT']}
                                            }
                                        },
                                        'LabelNameCondition': {
                                            'type': 'object',
                                            'properties': {'LabelName': {'type': 'string'}}
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                'DefaultBehavior': {'type': 'string', 'enum': ['KEEP', 'DROP']}
            }
        },
        managed_by_firewall_manager={'type': 'boolean'},
        log_type={'type': 'string', 'enum': ['WAF_LOGS']},
        log_scope={'type': 'string', 'enum': ['CUSTOMER', 'SECURITY_LAKE']}
    )

    permissions = ('wafv2:PutLoggingConfiguration',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client(
            'wafv2', region_name=self.manager.region)

        log_destination_arn = self.data.get('log_destination_arn')
        redacted_fields_data = self.data.get('redacted_fields', [])

        for r in resources:
            self.enable_waf_logging(client, r, log_destination_arn, redacted_fields_data)

    def enable_waf_logging(self, client, resource, log_destination_arn, redacted_fields_data=None,
                       managed_by_firewall_manager=False, logging_filter=None,
                       log_type="WAF_LOGS", log_scope=None):
        """
        Enable logging for a WAFv2 WebACL
        """

        valid_log_scopes = ["CUSTOMER", "SECURITY_LAKE"]
        if log_scope and log_scope not in valid_log_scopes:
            raise ValueError(f"Invalid log_scope value: {log_scope}."
                             f" Must be one of {valid_log_scopes}")

        if not log_scope:
            log_scope = "CUSTOMER"

        redacted_fields = []
        if redacted_fields_data:
            for f in redacted_fields_data:
                field = {}
                if f['type'] == 'SingleHeader':
                    field['SingleHeader'] = {'Name': f['data']}
                elif f['type'] == 'SingleQueryArgument':
                    field['SingleQueryArgument'] = {'Name': f['data']}
                elif f['type'] == 'AllQueryArguments':
                    field['AllQueryArguments'] = {}
                elif f['type'] == 'UriPath':
                    field['UriPath'] = {}
                elif f['type'] == 'QueryString':
                    field['QueryString'] = {}
                elif f['type'] == 'Body':
                    field['Body'] = {'OversizeHandling': f.get('oversize_handling', 'CONTINUE')}
                elif f['type'] == 'Method':
                    field['Method'] = {}
                elif f['type'] == 'JsonBody':
                    field['JsonBody'] = {
                        'MatchPattern': f.get('match_pattern', {}),
                        'MatchScope': f['match_scope'],
                        'InvalidFallbackBehavior': f.get('invalid_fallback_behavior', 'MATCH'),
                        'OversizeHandling': f.get('oversize_handling', 'CONTINUE')
                    }
                elif f['type'] == 'Headers':
                    field['Headers'] = {
                        'MatchPattern': f.get('match_pattern', {}),
                        'MatchScope': f['match_scope'],
                        'OversizeHandling': f.get('oversize_handling', 'CONTINUE')
                    }
                elif f['type'] == 'Cookies':
                    field['Cookies'] = {
                        'MatchPattern': f.get('match_pattern', {}),
                        'MatchScope': f['match_scope'],
                        'OversizeHandling': f.get('oversize_handling', 'CONTINUE')
                    }
                elif f['type'] == 'HeaderOrder':
                    field['HeaderOrder'] = {'OversizeHandling':
                                                f.get('oversize_handling', 'CONTINUE')}
                elif f['type'] == 'JA3Fingerprint':
                    field['JA3Fingerprint'] = {'FallbackBehavior':
                                                   f.get('fallback_behavior', 'MATCH')}
                redacted_fields.append(field)

        logging_configuration = {
            'ResourceArn': resource['ARN'],
            'LogDestinationConfigs': [log_destination_arn],
            'LogType': log_type,
            'LogScope': log_scope
        }

        if redacted_fields:
            logging_configuration['RedactedFields'] = redacted_fields

        if logging_filter:
            logging_configuration['LoggingFilter'] = logging_filter

        if managed_by_firewall_manager:
            logging_configuration['ManagedByFirewallManager'] = managed_by_firewall_manager

        client.put_logging_configuration(LoggingConfiguration=logging_configuration)
        self.log.info(f"Enabled logging for WAFv2 WebACL: {resource['Name']} ({resource['ARN']})")
