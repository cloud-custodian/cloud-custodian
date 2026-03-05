# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import PolicyValidationError
from .common import BaseTest


class ConfigRecorderTest(BaseTest):

    def test_config_recorder(self):
        factory = self.replay_flight_data('test_config_recorder')
        p = self.load_policy(
            {
                'name': 'recorder',
                'resource': 'aws.config-recorder',
                'filters': [
                    {'recordingGroup.allSupported': True},
                    {'recordingGroup.includeGlobalResourceTypes': True},
                    {'deliveryChannel.name': 'default'},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'default')

    def test_toggle_recording_stop(self):
        factory = self.replay_flight_data('test_config_recorder_toggle_stop')
        p = self.load_policy(
            {
                'name': 'stop-recording',
                'resource': 'aws.config-recorder',
                'filters': [{'type': 'value', 'key': 'status.recording', 'value': True}],
                'actions': [{'type': 'toggle-recording', 'enabled': False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('config')
        status = client.describe_configuration_recorder_status(
            ConfigurationRecorderNames=['default']
        )['ConfigurationRecordersStatus'][0]
        self.assertFalse(status['recording'])

    def test_toggle_recording_start(self):
        factory = self.replay_flight_data('test_config_recorder_toggle_start')
        p = self.load_policy(
            {
                'name': 'start-recording',
                'resource': 'aws.config-recorder',
                'filters': [{'type': 'value', 'key': 'status.recording', 'value': False}],
                'actions': [{'type': 'toggle-recording', 'enabled': True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('config')
        status = client.describe_configuration_recorder_status(
            ConfigurationRecorderNames=['default']
        )['ConfigurationRecordersStatus'][0]
        self.assertTrue(status['recording'])

    def test_config_recorder_cross_account(self):
        factory = self.replay_flight_data('test_config_recorder_cross_account')
        p = self.load_policy(
            {'name': 'recorder', 'resource': 'aws.config-recorder', 'filters': ['cross-account']},
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 1
        assert 'CrossAccountViolations' in resources[0]
        assert [
            (cav['AuthorizedAwsRegion'], cav['AuthorizedAccountId'])
            for cav in resources[0]['CrossAccountViolations']
        ] == [('us-east-1', '123456890123'), ('us-east-2', '123456890123')]


class ConfigComplianceTest(BaseTest):

    def test_config_with_inconsistent_hub_rule(self):
        factory = self.replay_flight_data('test_config_inconsistent_hub_rule')
        p = self.load_policy(
            {
                'name': 'compliance',
                'resource': 'aws.cloudtrail',
                'filters': [
                    {
                        'type': 'config-compliance',
                        'states': ['NON_COMPLIANT'],
                        'rules': ['securityhub-cloud-trail-encryption-enabled-dadfg6'],
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_compliance(self):
        factory = self.replay_flight_data('test_config_compliance')
        p = self.load_policy(
            {
                'name': 'compliance',
                'resource': 'ebs',
                'filters': [
                    {
                        'type': 'config-compliance',
                        'eval_filters': [
                            {
                                'EvaluationResultIdentifier.EvaluationResultQualifier.ResourceType': 'AWS::EC2::Volume'  # noqa: E501
                            }
                        ],
                        'rules': ['custodian-good-vol'],
                    }
                ],
            },
            session_factory=factory,
            config={'region': 'us-east-2'},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['VolumeId'], 'vol-0c6efd2a9f5677a03')
        self.assertEqual(
            resources[0]['c7n:config-compliance'][0]['Annotation'],
            'Resource is not compliant with policy:good-vol',
        )


class ConfigRuleTest(BaseTest):

    def test_validate(self):
        with self.assertRaises(PolicyValidationError) as ecm:
            self.load_policy(
                {
                    'name': 'rule',
                    'resource': 'ebs-snapshot',
                    'mode': {'role': 'arn:aws:iam', 'type': 'config-rule'},
                }
            )
        self.assertIn('AWS Config does not support resource-type:ebs-snapshot', str(ecm.exception))

    def test_status(self):
        session_factory = self.replay_flight_data("test_config_rule_status")
        p = self.load_policy(
            {
                "name": "rule",
                "resource": "config-rule",
                "filters": [
                    {"type": "status", "key": "FirstEvaluationStarted", "value": True},
                    {"tag:Environment": "sandbox"},
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        self.assertEqual(
            {
                "custodian-bucket-tags",
                "custodian-bucket-ver-tags",
                "custodian-db-tags",
            },
            {r["ConfigRuleName"] for r in resources},
        )

    def test_delete(self):
        session_factory = self.replay_flight_data("test_config_rule_delete")
        p = self.load_policy(
            {
                "name": "rule",
                "resource": "config-rule",
                "filters": [
                    {
                        "type": "value",
                        "key": "ConfigRuleName",
                        "value": "^custodian-db-",
                        "op": "regex",
                    },
                    {"tag:Environment": "sandbox"},
                ],
                "actions": ["delete"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        cr = resources.pop()
        client = session_factory().client("config")
        rules = client.describe_config_rules(ConfigRuleNames=[cr["ConfigRuleName"]]).get(
            "ConfigRules", []
        )
        self.assertEqual(rules[0]["ConfigRuleState"], "DELETING")

    def test_remediation(self):
        session_factory = self.replay_flight_data("test_config_rule_remediation")
        p = self.load_policy(
            {
                "name": "rule",
                "resource": "config-rule",
                "filters": [
                    {
                        "type": "remediation",
                        "rule_name": "config-managed-s3-bucket-public-write-remediate-event",
                        "remediation": {
                            "TargetId": "AWS-DisableS3BucketPublicReadWrite",
                            "Automatic": True,
                            "MaximumAutomaticAttempts": 5,
                            "RetryAttemptSeconds": 211,
                            "Parameters": {
                                "AutomationAssumeRole": {
                                    "StaticValue": {
                                        "Values": ["arn:aws:iam::{account_id}:role/myrole"]
                                    }
                                },
                                "S3BucketName": {"ResourceValue": {"Value": "RESOURCE_ID"}},
                            },
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        p.expand_variables(p.get_variables())
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['ConfigRuleName'],
            'custodian-config-managed-s3-bucket-public-write-remediate-event',
        )

    def test_remediation_no_results(self):
        session_factory = self.replay_flight_data("test_config_rule_remediation")
        policy = {
            "name": "rule",
            "resource": "config-rule",
            "filters": [
                {
                    "type": "remediation",
                    "rule_name": "i-dont-exist",
                }
            ],
        }
        p = self.load_policy(policy, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

        # Provide a valid rule name match but non-matching remediation config
        policy['filters'][0]['rule_name'] = 'config-managed-s3-bucket-public-write-remediate-event'
        policy['filters'][0]['remediation'] = {
            "TargetId": "intentionally-incorrect-target",
        }
        p = self.load_policy(policy, session_factory=session_factory)
        p.expand_variables(p.get_variables())
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_retention_filter(self):
        factory = self.replay_flight_data('test_configrecord_retention')

        p = self.load_policy(
            {
                'name': 'recorder',
                'resource': 'aws.config-recorder',
                'filters': [
                    {'type': 'retention', 'key': 'RetentionPeriodInDays', 'op': 'gte', 'value': 120}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 1
