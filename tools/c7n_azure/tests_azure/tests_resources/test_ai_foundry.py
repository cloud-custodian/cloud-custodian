# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import copy
import os
from unittest import mock

from parameterized import parameterized

import c7n.policy
from c7n import schema, utils
from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n_azure.constants import CONTAINER_EVENT_TRIGGER_MODE
from c7n_azure.resources import ai_foundry

from ..azure_common import (
    BaseTest,
    arm_template,
    cassette_name,
    requires_arm_polling,
    strict_cassette,
)


class AiFoundryDeploymentTest(BaseTest):
    def test_ai_foundry_deployment_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy(
                {
                    'name': 'test-azure-ai-foundry-deployment',
                    'resource': 'azure.ai-foundry-deployment',
                },
                validate=True,
            )
            self.assertTrue(p)

    @requires_arm_polling
    @arm_template('cognitive-service-deployment.json')
    @cassette_name('ai-foundry-deployment-get')
    def test_ai_foundry_deployment_get_resources(self):
        deployment_name = os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME')
        p = self.load_policy(
            {
                'name': 'test-azure-ai-foundry-deployment-get',
                'resource': 'azure.ai-foundry-deployment',
            }
        )

        resources = p.run()

        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(any(r['name'].endswith(deployment_name) for r in resources))

    def test_ai_foundry_deployment_tagging_not_implemented(self):
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    'name': 'test-tag-ai-foundry',
                    'resource': 'azure.ai-foundry-deployment',
                    'actions': [
                        {
                            'type': 'tag',
                            'tag': 'c7n_test_tag',
                            'value': 'true',
                        }
                    ],
                },
                validate=True,
            )

    @requires_arm_polling
    @arm_template('cognitive-service-deployment.json')
    @cassette_name('ai-foundry-deployment-delete')
    def test_z_ai_foundry_deployment_delete(self):
        read_policy = self.load_policy(
            {
                'name': 'test-azure-ai-foundry-deployment-read-before-delete',
                'resource': 'azure.ai-foundry-deployment',
            }
        )

        delete_policy = self.load_policy(
            {
                'name': 'test-azure-ai-foundry-deployment-delete',
                'resource': 'azure.ai-foundry-deployment',
                'actions': [{'type': 'delete'}],
            }
        )

        resources = read_policy.run()
        self.assertGreaterEqual(len(resources), 1)
        delete_policy.resource_manager.actions[0].process(resources)
        self.sleep_in_live_mode(10)

        remaining = read_policy.run()
        self.assertEqual(len(remaining), 0)


class CognitiveServiceTest(BaseTest):
    def test_cognitive_service_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-cognitive-service',
                'resource': 'azure.cognitiveservice'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cognitive-service.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-cog-serv',
            'resource': 'azure.cognitiveservice',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'cctest-cog-serv'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class CognitiveServiceUpdateTest(BaseTest):
    def test_update_example_targets_cognitive_services_with_local_auth(self) -> None:
        doc = schema.ElementSchema.doc(ai_foundry.CognitiveServiceUpdateAction)
        example = utils.yaml_load(doc.split('.. code-block:: yaml', 1)[1])['policies'][0]
        with self.sign_out_patch():
            policy = self.load_policy(example, validate=True)
        resources = [
            {
                'id': '/accounts/cognitive',
                'kind': 'CognitiveServices',
                'properties': {'disableLocalAuth': False},
            },
            {
                'id': '/accounts/already-disabled',
                'kind': 'CognitiveServices',
                'properties': {'disableLocalAuth': True},
            },
            {
                'id': '/accounts/openai',
                'kind': 'OpenAI',
                'properties': {'disableLocalAuth': False},
            },
            {
                'id': '/accounts/unverified',
                'kind': 'HealthInsights',
                'properties': {'disableLocalAuth': False},
            },
        ]
        manager = policy.resource_manager
        selected = manager.filter_resources(resources)
        self.assertEqual([r['id'] for r in selected], ['/accounts/cognitive'])
        session = mock.Mock()
        session.resource_api_version.return_value = '2025-06-01'
        with mock.patch.object(manager, 'get_session', return_value=session), \
                mock.patch.object(manager, 'get_client') as get_client:
            manager.actions[0].process(selected)
            update = get_client.return_value.resources.begin_update_by_id
            self.assertEqual(
                [(call.args[0], call.args[2].serialize()) for call in update.call_args_list],
                [('/accounts/cognitive', {'properties': {'disableLocalAuth': True}})],
            )

    @parameterized.expand([
        ('local_auth_on', {'disableLocalAuth': False}),
        ('local_auth_off', {'disableLocalAuth': True}),
        ('public_access_on', {'publicNetworkAccess': 'Enabled'}),
        ('public_access_off', {'publicNetworkAccess': 'Disabled'}),
        ('dynamic_on', {'dynamicThrottlingEnabled': True}),
        ('dynamic_off', {'dynamicThrottlingEnabled': False}),
        ('outbound_restricted', {'restrictOutboundNetworkAccess': True}),
        ('outbound_unrestricted', {'restrictOutboundNetworkAccess': False}),
        ('fqdns', {'allowedFqdnList': ['example.com']}),
        ('clear_fqdns', {'allowedFqdnList': []}),
        ('network_allow', {'networkAcls': {'defaultAction': 'Allow'}}),
        ('network_deny', {'networkAcls': {'defaultAction': 'Deny'}}),
        ('ip_rules', {'networkAcls': {'ipRules': [{'value': '192.0.2.2'}]}}),
        ('clear_ip_rules', {'networkAcls': {'ipRules': []}}),
        ('bypass_services', {'networkAcls': {'bypass': 'AzureServices'}}),
        ('bypass_none', {'networkAcls': {'bypass': 'None'}}),
        ('statistics_on', {'apiProperties': {'statisticsEnabled': True}}),
        ('statistics_off', {'apiProperties': {'statisticsEnabled': False}}),
    ])
    def test_update_writable_property(self, name: str, properties: dict) -> None:
        policy = self._load_update_policy(properties)
        self.assertEqual(
            policy.resource_manager.actions[0].data['properties'],
            properties,
        )

    @parameterized.expand([
        ('migrationToken', 'token'),
        ('customSubDomainName', 'c7n-account'),
        ('encryption', {'keySource': 'Microsoft.CognitiveServices'}),
        ('userOwnedStorage', [{'resourceId': '/storage'}]),
        ('amlWorkspace', {'resourceId': '/workspace'}),
        ('restore', True),
        ('locations', {'routingMethod': 'Weighted'}),
        ('raiMonitorConfig', {'adxStorageResourceId': '/storage'}),
        ('networkInjections', [{'scenario': 'agent'}]),
        ('allowProjectManagement', True),
        ('defaultProject', 'project'),
        ('associatedProjects', ['project']),
    ])
    def test_update_excluded_property(self, name: str, value: object) -> None:
        with self.assertRaises(PolicyValidationError):
            self._load_update_policy({name: value})

    @parameterized.expand([
        ('readonly', {'provisioningState': 'Succeeded'}),
        ('unknown', {'notWritable': True}),
        ('boolean_type', {'disableLocalAuth': 'true'}),
        ('public_access_enum', {'publicNetworkAccess': 'Private'}),
        ('null', {'disableLocalAuth': None}),
        ('dynamic_type', {'dynamicThrottlingEnabled': 1}),
        ('outbound_type', {'restrictOutboundNetworkAccess': 'true'}),
        ('fqdn_type', {'allowedFqdnList': 'example.com'}),
        ('fqdn_item', {'allowedFqdnList': [True]}),
        ('network_type', {'networkAcls': []}),
        ('network_action', {'networkAcls': {'defaultAction': 'Block'}}),
        ('network_bypass', {'networkAcls': {'bypass': 'All'}}),
        ('ip_rule_type', {'networkAcls': {'ipRules': ['192.0.2.1']}}),
        ('ip_rule_value', {'networkAcls': {'ipRules': [{'value': 42}]}}),
        ('ip_rule_required', {'networkAcls': {'ipRules': [{}]}}),
        ('ip_rule_unknown', {
            'networkAcls': {'ipRules': [{'value': '1.2.3.4', 'x': 1}]},
        }),
        ('vnet_excluded', {'networkAcls': {'virtualNetworkRules': []}}),
        ('network_unknown', {'networkAcls': {'other': True}}),
        ('statistics_type', {'apiProperties': {'statisticsEnabled': 'true'}}),
        ('api_excluded', {'apiProperties': {'aadClientId': 'client'}}),
        ('metadata', {'kinds': ['CognitiveServices']}),
        ('nested_metadata', {'networkAcls': {'kinds': ['CognitiveServices']}}),
    ])
    def test_update_invalid_property(self, name: str, properties: dict) -> None:
        with self.assertRaises(PolicyValidationError):
            self._load_update_policy(properties)

    def test_update_requires_properties(self) -> None:
        with self.sign_out_patch():
            self.assertRaises(
                PolicyValidationError,
                self.load_policy,
                {
                    'name': 'update-account',
                    'resource': 'azure.cognitiveservice',
                    'actions': [{'type': 'update'}],
                },
                validate=True,
            )

    @parameterized.expand([
        ('AIServices', ('apiProperties.statisticsEnabled',)),
        ('CognitiveServices', ()),
        ('ComputerVision', ('networkAcls.bypass', 'apiProperties.statisticsEnabled')),
        ('ContentModerator', ('networkAcls.bypass', 'apiProperties.statisticsEnabled')),
        ('ContentSafety', (
            'dynamicThrottlingEnabled',
            'networkAcls.bypass',
            'apiProperties.statisticsEnabled',
        )),
        ('CustomVision.Prediction', (
            'networkAcls.bypass',
            'apiProperties.statisticsEnabled',
        )),
        ('CustomVision.Training', (
            'dynamicThrottlingEnabled',
            'networkAcls.bypass',
            'apiProperties.statisticsEnabled',
        )),
        ('Face', (
            'dynamicThrottlingEnabled',
            'networkAcls.bypass',
            'apiProperties.statisticsEnabled',
        )),
        ('FormRecognizer', ('networkAcls.bypass', 'apiProperties.statisticsEnabled')),
        ('ImmersiveReader', ('networkAcls.bypass', 'apiProperties.statisticsEnabled')),
        ('OpenAI', ('dynamicThrottlingEnabled',)),
        ('QnAMaker.v2', ('networkAcls.bypass', 'apiProperties.statisticsEnabled')),
        ('SpeechServices', (
            'dynamicThrottlingEnabled',
            'networkAcls.bypass',
            'apiProperties.statisticsEnabled',
        )),
        ('TextAnalytics', ('apiProperties.statisticsEnabled',)),
        ('TextTranslation', (
            'dynamicThrottlingEnabled',
            'networkAcls.bypass',
            'apiProperties.statisticsEnabled',
        )),
        ('HealthInsights', (
            'disableLocalAuth',
            'publicNetworkAccess',
            'dynamicThrottlingEnabled',
            'restrictOutboundNetworkAccess',
            'allowedFqdnList',
            'networkAcls.defaultAction',
            'networkAcls.ipRules',
            'networkAcls.bypass',
            'apiProperties.statisticsEnabled',
        )),
    ])
    def test_update_kind_support(self, kind: str, unsupported: tuple[str, ...]) -> None:
        settings = [
            ('disableLocalAuth', {'disableLocalAuth': True}),
            ('publicNetworkAccess', {'publicNetworkAccess': 'Disabled'}),
            ('dynamicThrottlingEnabled', {'dynamicThrottlingEnabled': True}),
            ('restrictOutboundNetworkAccess', {'restrictOutboundNetworkAccess': True}),
            ('allowedFqdnList', {'allowedFqdnList': ['example.com']}),
            ('networkAcls.defaultAction', {'networkAcls': {'defaultAction': 'Deny'}}),
            ('networkAcls.ipRules', {'networkAcls': {'ipRules': []}}),
            ('networkAcls.bypass', {'networkAcls': {'bypass': 'AzureServices'}}),
            ('apiProperties.statisticsEnabled', {
                'apiProperties': {'statisticsEnabled': True},
            }),
        ]
        resource = {'id': '/accounts/account', 'kind': kind, 'properties': {}}
        for field, properties in settings:
            with self.subTest(field=field):
                policy = self._load_update_policy(properties)
                manager = policy.resource_manager
                session = mock.Mock()
                session.resource_api_version.return_value = '2025-06-01'
                with mock.patch.object(manager, 'get_session', return_value=session), \
                        mock.patch.object(manager, 'get_client') as get_client:
                    if field in unsupported:
                        with self.assertRaises(PolicyExecutionError) as error:
                            manager.actions[0].process([resource])
                        self.assertIn(field, str(error.exception))
                        self.assertIn(kind, str(error.exception))
                        get_client.assert_not_called()
                    else:
                        manager.actions[0].process([resource])
                        update = get_client.return_value.resources.begin_update_by_id
                        self.assertEqual(update.call_args.args[:2], (
                            resource['id'], '2025-06-01',
                        ))
                        self.assertEqual(
                            update.call_args.args[2].serialize(),
                            {'properties': properties},
                        )
                        update.return_value.result.assert_called_once_with()

    def test_update_preflights_all_accounts_before_writing(self) -> None:
        policy = self._load_update_policy({'dynamicThrottlingEnabled': True})
        resources = [
            {'id': '/accounts/first', 'kind': 'CognitiveServices'},
            {'id': '/accounts/second', 'kind': 'ContentSafety'},
        ]
        with mock.patch.object(policy.resource_manager, 'get_client') as get_client:
            with self.assertRaises(PolicyExecutionError):
                policy.resource_manager.actions[0].process(resources)
            get_client.assert_not_called()

    @parameterized.expand([
        ('scalar', {'disableLocalAuth': True}, {'disableLocalAuth': True}),
        ('network_action', {'networkAcls': {'defaultAction': 'Deny'}}, {
            'networkAcls': {
                'defaultAction': 'Deny',
                'ipRules': [{'value': '192.0.2.1'}],
                'bypass': 'AzureServices',
                'virtualNetworkRules': [
                    {'id': '/subnets/subnet', 'state': 'Succeeded'},
                ],
            },
        }),
        ('clear_ips', {'networkAcls': {'ipRules': []}}, {
            'networkAcls': {
                'defaultAction': 'Allow',
                'ipRules': [],
                'bypass': 'AzureServices',
                'virtualNetworkRules': [
                    {'id': '/subnets/subnet', 'state': 'Succeeded'},
                ],
            },
        }),
        ('statistics', {'apiProperties': {'statisticsEnabled': True}}, {
            'apiProperties': {'statisticsEnabled': True},
        }),
        ('clear_fqdns', {'allowedFqdnList': []}, {'allowedFqdnList': []}),
    ])
    def test_update_request_preserves_siblings(
        self,
        name: str,
        properties: dict,
        expected: dict,
    ) -> None:
        resource = {
            'id': '/accounts/account',
            'kind': 'CognitiveServices',
            'properties': {
                'provisioningState': 'Succeeded',
                'endpoint': 'https://example.com',
                'disableLocalAuth': False,
                'publicNetworkAccess': 'Enabled',
                'allowedFqdnList': ['example.com'],
                'networkAcls': {
                    'defaultAction': 'Allow',
                    'ipRules': [{'value': '192.0.2.1'}],
                    'bypass': 'AzureServices',
                    'virtualNetworkRules': [
                        {'id': '/subnets/subnet', 'state': 'Succeeded'},
                    ],
                },
                'apiProperties': {'statisticsEnabled': False},
            },
        }
        original = copy.deepcopy((resource, properties))
        policy = self._load_update_policy(properties)
        manager = policy.resource_manager
        session = mock.Mock()
        session.resource_api_version.return_value = '2025-06-01'
        with mock.patch.object(manager, 'get_session', return_value=session), \
                mock.patch.object(manager, 'get_client') as get_client:
            manager.actions[0].process([resource])
            update = get_client.return_value.resources.begin_update_by_id
            self.assertEqual(
                update.call_args.args[2].serialize(),
                {'properties': expected},
            )
        self.assertEqual((resource, properties), original)

    def _load_update_policy(self, properties: dict) -> c7n.policy.Policy:
        with self.sign_out_patch():
            return self.load_policy(
                {
                    'name': 'update-account',
                    'resource': 'azure.cognitiveservice',
                    'actions': [{'type': 'update', 'properties': properties}],
                },
                validate=True,
            )


@requires_arm_polling
class CognitiveServiceUpdateFunctionalTest(BaseTest):
    recording_resource_group = 'test_cognitive-service-update'

    @parameterized.expand([
        ('pull', False),
        ('event', True),
    ])
    @strict_cassette(None)
    @arm_template('cognitive-service-update.json')
    def test_update_account(self, name: str, event_triggered: bool) -> None:
        read_policy = self.load_policy({
            'name': 'read-update-test-account',
            'resource': 'azure.cognitiveservice',
            'filters': [{'resourceGroup': self.recording_resource_group}],
        })
        before = read_policy.run()
        self.assertEqual(len(before), 1)
        resource = before[0]
        self.assertEqual(resource['kind'], 'CognitiveServices')
        settings = [
            {
                'disableLocalAuth': True,
                'publicNetworkAccess': 'Disabled',
                'dynamicThrottlingEnabled': True,
                'restrictOutboundNetworkAccess': True,
                'allowedFqdnList': ['example.com'],
                'networkAcls': {
                    'defaultAction': 'Deny',
                    'ipRules': [{'value': '192.0.2.2'}],
                    'bypass': 'AzureServices',
                },
                'apiProperties': {'statisticsEnabled': True},
            },
            {
                'disableLocalAuth': False,
                'publicNetworkAccess': 'Enabled',
                'dynamicThrottlingEnabled': False,
                'restrictOutboundNetworkAccess': False,
                'allowedFqdnList': [],
                'networkAcls': {
                    'defaultAction': 'Allow',
                    'ipRules': [],
                    'bypass': 'None',
                },
                'apiProperties': {'statisticsEnabled': False},
            },
        ]
        for properties in settings:
            policy_data = {
                'name': 'update-cognitive-service-account',
                'resource': 'azure.cognitiveservice',
                'filters': [{'id': resource['id']}],
                'actions': [{'type': 'update', 'properties': properties}],
            }
            if event_triggered:
                policy_data['mode'] = {
                    'type': CONTAINER_EVENT_TRIGGER_MODE,
                    'events': ['CognitiveServiceWrite'],
                }
            policy = self.load_policy(policy_data, validate=True)
            if event_triggered:
                resources = policy.push(
                    {
                        'subject': resource['id'],
                        'eventTime': '2026-10-16T00:00:00Z',
                        'id': 'cognitive-service-update',
                    },
                    None,
                )
            else:
                resources = policy.run()
            self.assertEqual([r['id'] for r in resources], [resource['id']])
            after = read_policy.run()
            self.assertEqual(len(after), 1)
            updated = after[0]['properties']
            for key, expected in properties.items():
                with self.subTest(property=key, expected=expected):
                    if isinstance(expected, dict):
                        for nested, value in expected.items():
                            self.assertEqual(updated[key][nested], value)
                    else:
                        self.assertEqual(updated[key], expected)
            self.assertEqual(
                updated['customSubDomainName'],
                resource['properties']['customSubDomainName'],
            )


class AiFoundryCognitiveServiceDeploymentTest(BaseTest):
    def test_cognitiveservice_deployment_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy(
                {
                    'name': 'test-azure-cognitiveservice-deployment',
                    'resource': 'azure.cognitiveservice-deployment',
                },
                validate=True,
            )
            self.assertTrue(p)

    @requires_arm_polling
    @arm_template('cognitive-service-deployment.json')
    @cassette_name('ai-foundry-cognitiveservice-deployment-get')
    def test_cognitiveservice_deployment_get_resources(self):
        deployment_name = os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME')
        p = self.load_policy(
            {
                'name': 'test-azure-cognitiveservice-deployment-get',
                'resource': 'azure.cognitiveservice-deployment',
            }
        )

        resources = p.run()

        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(any(r['name'].endswith(deployment_name) for r in resources))

    @requires_arm_polling
    @arm_template('cognitive-service-deployment.json')
    @cassette_name('ai-foundry-cognitiveservice-deployment-metric')
    def test_cognitiveservice_deployment_metric_filter(self):
        deployment_name = os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME', 'cctest-gpt4o-mini')
        p = self.load_policy(
            {
                'name': 'test-azure-cognitiveservice-deployment-metric',
                'resource': 'azure.cognitiveservice-deployment',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'glob',
                     'value': '*' + deployment_name},
                    {'type': 'metric',
                     'metric': 'AzureOpenAIRequests',
                     'metric_namespace': 'Microsoft.CognitiveServices/accounts',
                     'aggregation': 'total',
                     'op': 'lte',
                     'threshold': 0,
                     'timeframe': 168,
                     'interval': 'P1D',
                     'no_data_action': 'to_zero',
                     'dimensions': [
                         {'name': 'ModelDeploymentName', 'value': 'resource-name'}]}],
            },
            validate=True,
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)

    def test_cognitiveservice_deployment_tagging_not_implemented(self):
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    'name': 'test-tag-cognitiveservice-deployment',
                    'resource': 'azure.cognitiveservice-deployment',
                    'actions': [
                        {
                            'type': 'tag',
                            'tag': 'c7n_test_tag',
                            'value': 'true',
                        }
                    ],
                },
                validate=True,
            )

    @requires_arm_polling
    @arm_template('cognitive-service-deployment.json')
    @cassette_name('ai-foundry-cognitiveservice-deployment-delete')
    def test_z_cognitiveservice_deployment_delete(self):
        read_policy = self.load_policy(
            {
                'name': 'test-azure-cognitiveservice-deployment-read-before-delete',
                'resource': 'azure.cognitiveservice-deployment',
            }
        )

        delete_policy = self.load_policy(
            {
                'name': 'test-azure-cognitiveservice-deployment-delete',
                'resource': 'azure.cognitiveservice-deployment',
                'actions': [{'type': 'delete'}],
            }
        )

        resources = read_policy.run()
        self.assertGreaterEqual(len(resources), 1)
        delete_policy.resource_manager.actions[0].process(resources)
        self.sleep_in_live_mode(10)

        remaining = read_policy.run()
        self.assertEqual(len(remaining), 0)


class AIFoundryProjectTest(BaseTest):
    def test_ai_foundry_project_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-project',
                'resource': 'azure.ai-foundry-project'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('ai-foundry-project.json')
    @cassette_name('ai-foundry-projects-query')
    def test_ai_foundry_project_query(self):
        p = self.load_policy({
            'name': 'test-ai-foundry-project-query',
            'resource': 'azure.ai-foundry-project',
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertIn('/projects/', resources[0].get('id', '').lower())

    @arm_template('ai-foundry-project.json')
    @cassette_name('ai-foundry-projects-filter')
    def test_ai_foundry_project_filter(self):
        p = self.load_policy({
            'name': 'test-ai-foundry-project-filter',
            'resource': 'azure.ai-foundry-project',
            'filters': [{
                'type': 'value',
                'key': 'id',
                'op': 'contains',
                'value': '/projects/cctest-aifoundry-project'
            }]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn('/projects/cctest-aifoundry-project', resources[0].get('id', '').lower())


class AIFoundryConnectionTest(BaseTest):
    def test_ai_foundry_connection_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-connection',
                'resource': 'azure.ai-foundry-connection'
            }, validate=True)
            self.assertTrue(p)

    def test_ai_foundry_connection_tag_not_supported(self):
        with self.sign_out_patch():
            policy = {
                'name': 'test-ai-foundry-connection-tag',
                'resource': 'azure.ai-foundry-connection',
                'actions': [{'type': 'tag', 'tags': {'env': 'test'}}]
            }
            self.assertRaises(
                PolicyValidationError, self.load_policy, policy, validate=True
            )

    def test_ai_foundry_connection_update_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-connection-update',
                'resource': 'azure.ai-foundry-connection',
                'actions': [{
                    'type': 'update',
                    'properties': {
                        'isSharedToAll': True
                    }
                }]
            }, validate=True)
            self.assertTrue(p)

    def test_ai_foundry_connection_update_invalid_field(self):
        with self.sign_out_patch():
            policy = {
                'name': 'test-ai-foundry-connection-update-invalid-field',
                'resource': 'azure.ai-foundry-connection',
                'actions': [{
                    'type': 'update',
                    'properties': {
                        'notWritableField': 'x'
                    }
                }]
            }
            self.assertRaises(
                PolicyValidationError, self.load_policy, policy, validate=True
            )

    def test_ai_foundry_connection_delete_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-connection-delete',
                'resource': 'azure.ai-foundry-connection',
                'actions': [{'type': 'delete'}]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('ai-foundry-connection.json')
    @cassette_name('ai-foundry-connections-query')
    def test_ai_foundry_connection_query(self):
        project_policy = self.load_policy({
            'name': 'test-ai-foundry-project-prereq',
            'resource': 'azure.ai-foundry-project',
        })

        projects = project_policy.run()
        self.assertGreaterEqual(len(projects), 1)

        p = self.load_policy({
            'name': 'test-ai-foundry-connection-query',
            'resource': 'azure.ai-foundry-connection',
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertIn('/connections/', resources[0].get('id', '').lower())

    @arm_template('ai-foundry-connection.json')
    @cassette_name('ai-foundry-connections-filter')
    def test_ai_foundry_connection_filter(self):
        read_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-read-for-filter',
            'resource': 'azure.ai-foundry-connection',
        })

        resources = read_policy.run()
        self.assertGreaterEqual(len(resources), 1)

        target_name = resources[0]['name']
        filter_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-filter',
            'resource': 'azure.ai-foundry-connection',
            'filters': [{
                'type': 'value',
                'key': 'name',
                'op': 'eq',
                'value': target_name
            }]
        })

        filtered = filter_policy.run()
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['name'], target_name)

    @arm_template('ai-foundry-connection.json')
    @cassette_name('ai-foundry-connections-update')
    def test_ai_foundry_connection_update(self):
        read_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-read-before-update',
            'resource': 'azure.ai-foundry-connection',
        })

        before = read_policy.run()
        self.assertEqual(len(before), 1)
        current = before[0].get('properties', {}).get('isSharedToAll', False)
        updated = not current

        update_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-update',
            'resource': 'azure.ai-foundry-connection',
            'actions': [{
                'type': 'update',
                'properties': {
                    'isSharedToAll': updated
                }
            }]
        })

        update_policy.run()
        self.sleep_in_live_mode(10)

        after = read_policy.run()
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].get('properties', {}).get('isSharedToAll'), updated)

    @arm_template('ai-foundry-connection.json')
    @cassette_name('ai-foundry-connections-delete')
    def test_z_ai_foundry_connection_delete(self):
        read_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-read-before-delete',
            'resource': 'azure.ai-foundry-connection',
        })

        delete_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-delete',
            'resource': 'azure.ai-foundry-connection',
            'actions': [{'type': 'delete'}],
        })

        resources = read_policy.run()
        self.assertEqual(len(resources), 1)
        delete_policy.resource_manager.actions[0].process(resources)
        self.sleep_in_live_mode(10)

        remaining = read_policy.run()
        self.assertEqual(len(remaining), 0)


class AIFoundryApplicationTest(BaseTest):
    def test_ai_foundry_application_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-application',
                'resource': 'azure.ai-foundry-application'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('ai-foundry-application.json')
    @cassette_name('ai-foundry-applications')
    def test_ai_foundry_application_query(self):
        project_policy = self.load_policy({
            'name': 'test-ai-foundry-project-prereq',
            'resource': 'azure.ai-foundry-project',
        })

        projects = project_policy.run()
        self.assertGreaterEqual(len(projects), 1)

        p = self.load_policy({
            'name': 'test-ai-foundry-application-query',
            'resource': 'azure.ai-foundry-application',
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(
            any(r.get('id', '').lower().endswith('/applications/cctest-aifoundry-application')
                for r in resources)
        )

    @arm_template('ai-foundry-application.json')
    @cassette_name('ai-foundry-applications-filter')
    def test_ai_foundry_application_filter_by_name(self):
        project_policy = self.load_policy({
            'name': 'test-ai-foundry-project-prereq-filter',
            'resource': 'azure.ai-foundry-project',
        })

        projects = project_policy.run()
        self.assertGreaterEqual(len(projects), 1)

        p = self.load_policy({
            'name': 'test-ai-foundry-application-filter-name',
            'resource': 'azure.ai-foundry-application',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cctest-aifoundry-application'
                }
            ]
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(all(r.get('name') == 'cctest-aifoundry-application' for r in resources))


class AIFoundryAgentTest(BaseTest):

    def test_ai_foundry_agent_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-agent',
                'resource': 'azure.ai-foundry-agent'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('ai-foundry-application.json')
    @cassette_name('ai-foundry-agents')
    def test_ai_foundry_agent_query(self):
        app_policy = self.load_policy({
            'name': 'test-ai-foundry-application-prereq',
            'resource': 'azure.ai-foundry-application',
        })

        applications = app_policy.run()
        self.assertGreaterEqual(len(applications), 1)

        p = self.load_policy({
            'name': 'test-ai-foundry-agent-query',
            'resource': 'azure.ai-foundry-agent',
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(any('/agents/' in r.get('id', '').lower() for r in resources))

    @arm_template('ai-foundry-application.json')
    @cassette_name('ai-foundry-agents-filter')
    def test_ai_foundry_agent_filter_by_name(self):
        app_policy = self.load_policy({
            'name': 'test-ai-foundry-application-prereq-filter',
            'resource': 'azure.ai-foundry-application',
        })

        applications = app_policy.run()
        self.assertGreaterEqual(len(applications), 1)

        p = self.load_policy({
            'name': 'test-ai-foundry-agent-filter-name',
            'resource': 'azure.ai-foundry-agent',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value': 'cctest-aifoundry-agent-*'
                }
            ]
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(
            all(r.get('name', '').startswith('cctest-aifoundry-agent-') for r in resources)
        )
