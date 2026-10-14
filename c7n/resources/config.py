# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.filters import Filter, ValueFilter, CrossAccountAccessFilter
from c7n.manager import resources
from c7n.resolver import ValuesFrom
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.utils import local_session, chunks, type_schema
from c7n.tags import universal_augment


class RecorderDescribe(DescribeSource):

    def augment(self, resources):
        # in general we don't to default augmentation beyond tags, to
        # avoid extraneous api calls. in this case config recorder is
        # a singleton (so no cardinality issues in terms of api calls)
        # and the common case is looking checking against all of the
        # attributes to ensure proper configuration.
        client = local_session(self.manager.session_factory).client('config')
        for r in resources:
            status = client.describe_configuration_recorder_status(
                ConfigurationRecorderNames=[r['name']]
            )['ConfigurationRecordersStatus']
            if status:
                r.update({'status': status.pop()})

            channels = client.describe_delivery_channels().get('DeliveryChannels')
            if channels:
                r.update({'deliveryChannel': channels.pop()})
        return resources


@resources.register('config-recorder')
class ConfigRecorder(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "config"
        enum_spec = ('describe_configuration_recorders', 'ConfigurationRecorders', None)
        id = name = "name"
        filter_name = 'ConfigurationRecorderNames'
        filter_type = 'list'
        arn = False
        config_type = cfn_type = 'AWS::Config::ConfigurationRecorder'

    source_mapping = {'describe': RecorderDescribe, 'config': ConfigSource}


@ConfigRecorder.action_registry.register('toggle-recording')
class ToggleRecording(BaseAction):
    """Start or stop the AWS Config configuration recorder.

    :example:

    .. code-block:: yaml

        policies:
          - name: stop-config-recording
            resource: config-recorder
            filters:
              - type: value
                key: status.recording
                value: true
            actions:
              - type: toggle-recording
                enabled: false
    """

    schema = type_schema('toggle-recording', enabled={'type': 'boolean', 'default': True})
    permissions = (
        'config:StartConfigurationRecorder',
        'config:StopConfigurationRecorder',
    )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('config')
        enabled = self.data.get('enabled', True)
        for r in resources:
            if enabled:
                client.start_configuration_recorder(ConfigurationRecorderName=r['name'])
            else:
                client.stop_configuration_recorder(ConfigurationRecorderName=r['name'])


@ConfigRecorder.filter_registry.register('cross-account')
class ConfigCrossAccountFilter(CrossAccountAccessFilter):

    schema = type_schema(
        'cross-account',
        # white list accounts
        allowed_regions={'type': 'array', 'items': {'type': 'string'}},
        whitelist_from=ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}},
    )

    permissions = ('config:DescribeAggregationAuthorizations',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('config')

        allowed_accounts = set(self.get_accounts())
        allowed_regions = set(self.data.get('allowed_regions', ()))

        matched = []
        auths = client.describe_aggregation_authorizations().get('AggregationAuthorizations', [])

        for a in auths:
            if a['AuthorizedAccountId'] not in allowed_accounts or (
                allowed_regions and a['AuthorizedAwsRegion'] not in allowed_regions
            ):
                matched.append(a)

        # only 1 config recorder per account
        resources[0][self.annotation_key] = matched
        return resources


@ConfigRecorder.filter_registry.register("retention")
class ConfigRetentionConfigurations(ValueFilter):
    """
    Filter to look for config retention configurations

    AWS Config supports only one retention configuration per region in a particular account.

    RetentionPeriodInDays value should be an integer ranging from 30 to 2557

    :example:

    .. code-block:: yaml

        policies:
        - name: config-recorder-verify-retention
          resource: config-recorder
          filters:
            - type: retention
              key: RetentionPeriodInDays
              value: 30

    Also retrieves the retention configuration if no key/value is provided:

    :example:

    .. code-block:: yaml

        policies:
        - name: config-recorder
          resource: config-recorder
          filters:
            - type: retention
    """

    schema = type_schema(
        "retention",
        rinherit=ValueFilter.schema,
    )
    schema_alias = False
    permissions = ("config:DescribeRetentionConfigurations",)
    annotation_key = "c7n:ConfigRetentionConfigs"

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client("config")

        retention_configs = client.describe_retention_configurations().get(
            "RetentionConfigurations", []
        )
        retention_config = retention_configs and retention_configs[0] or {}
        for resource in resources:
            resource[self.annotation_key] = retention_config
        return super().process(resources, event)

    def __call__(self, resource):
        return super().__call__(resource[self.annotation_key])


@resources.register('config-rule')
class ConfigRule(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "config"
        enum_spec = ("describe_config_rules", "ConfigRules", None)
        id = name = "ConfigRuleName"
        arn = "ConfigRuleArn"
        arn_type = 'config-rule'
        filter_name = 'ConfigRuleNames'
        filter_type = 'list'
        cfn_type = 'AWS::Config::ConfigRule'
        universal_taggable = True

    augment = universal_augment


@ConfigRule.filter_registry.register('status')
class RuleStatus(ValueFilter):

    schema = type_schema('status', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('config:DescribeConfigRuleEvaluationStatus',)
    annotate = False

    def process(self, resources, event=None):
        status_map = {}
        client = local_session(self.manager.session_factory).client('config')

        for rule_set in chunks(resources, 100):
            for status in client.describe_config_rule_evaluation_status(
                ConfigRuleNames=[r['ConfigRuleName'] for r in rule_set]
            ).get('ConfigRulesEvaluationStatus', []):
                status_map[status['ConfigRuleName']] = status

        results = []
        for r in resources:
            r['c7n:status'] = status_map.get(r['ConfigRuleName'])
            if self.match(r['c7n:status']):
                results.append(r)
        return results


@ConfigRule.action_registry.register('delete')
class DeleteRule(BaseAction):

    schema = type_schema('delete')
    permissions = ('config:DeleteConfigRule',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('config')
        for r in resources:
            client.delete_config_rule(ConfigRuleName=r['ConfigRuleName'])


@ConfigRule.filter_registry.register('remediation')
class RuleRemediation(Filter):
    """Filter to look for config rules that match the given remediation configuration settings

    This filter can be used in conjunction with account missing filter to look for
    managed config rules with missing remediation and to enable it accordingly.

    :example:

    .. code-block:: yaml

        policies:
          - name: config-managed-s3-bucket-public-write-remediate-event-with-filter
            description: |
              This policy detects if S3 bucket allows public write by the bucket policy
              or ACL and remediates.
            comment: |
              This policy detects if S3 bucket policy or ACL allows public write access.
              When the bucket is evaluated as 'NON_COMPLIANT', the action
              'AWS-DisableS3BucketPublicReadWrite' is triggered and remediates.
            resource: account
            filters:
              - type: missing
                policy:
                  resource: config-rule
                  filters:
                    - type: remediation
                      rule_name: &rule_name 'config-managed-s3-bucket-public-write-remediate-event'
                      remediation: &remediation-config
                        TargetId: AWS-DisableS3BucketPublicReadWrite
                        Automatic: true
                        MaximumAutomaticAttempts: 5
                        RetryAttemptSeconds: 211
                        Parameters:
                          AutomationAssumeRole:
                            StaticValue:
                              Values:
                                - 'arn:aws:iam::{account_id}:role/myrole'
                          S3BucketName:
                            ResourceValue:
                              Value: RESOURCE_ID
            actions:
              - type: toggle-config-managed-rule
                rule_name: *rule_name
                managed_rule_id: S3_BUCKET_PUBLIC_WRITE_PROHIBITED
                resource_types:
                  - 'AWS::S3::Bucket'
                rule_parameters: '{}'
                remediation: *remediation-config
    """

    schema = type_schema(
        'remediation',
        rule_name={'type': 'string'},
        rule_prefix={'type': 'string'},
        remediation={
            'type': 'object',
            'properties': {
                'target_type': {'type': 'string'},
                'target_id': {'type': 'string'},
                'automatic': {'type': 'boolean'},
                'parameters': {'type': 'object'},
                'maximum_automatic_attempts': {
                    'type': 'integer',
                    'minimum': 1,
                    'maximum': 25,
                },
                'retry_attempt_seconds': {
                    'type': 'integer',
                    'minimum': 1,
                    'maximum': 2678000,
                },
                'execution_controls': {'type': 'object'},
            },
        },
    )

    schema_alias = False
    permissions = ('config:DescribeRemediationConfigurations',)

    def process(self, resources, event=None):
        prefix = self.data.get('rule_prefix', 'custodian-')
        rule_name = "%s%s" % (prefix, self.data['rule_name'])
        results = [r for r in resources if r['ConfigRuleName'] == rule_name]

        # no matched rule
        if not results:
            return []

        client = local_session(self.manager.session_factory).client('config')
        resp = client.describe_remediation_configurations(ConfigRuleNames=[rule_name])

        desired_remediation_config = self.data['remediation']
        desired_remediation_config['ConfigRuleName'] = rule_name
        if 'TargetType' not in desired_remediation_config:
            desired_remediation_config['TargetType'] = 'SSM_DOCUMENT'

        # check if matched rule has matched remediation configuration
        for r in resp.get('RemediationConfigurations', []):
            r.pop('Arn', None)  # don't include this for comparison
            if r == desired_remediation_config:
                return results

        return []
