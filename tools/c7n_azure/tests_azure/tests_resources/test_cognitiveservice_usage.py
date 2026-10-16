# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import io
import json
from types import SimpleNamespace
from unittest import mock

import requests
import urllib3

import c7n.policy

from c7n.exceptions import PolicyValidationError
from c7n_azure.session import Session

from ..azure_common import BaseTest, arm_template


class CognitiveServiceUsageUnitTest(BaseTest):
    parent = {
        'id': '/subscriptions/test/resourceGroups/usage-test/providers/'
        'Microsoft.CognitiveServices/accounts/account-one',
        'name': 'account-one',
        'resourceGroup': 'usage-test',
    }

    def load_usage_policy(self, **data: object) -> c7n.policy.Policy:
        with self.sign_out_patch():
            return self.load_policy(
                {
                    'name': 'test-cognitiveservice-usage',
                    'resource': 'azure.cognitiveservice-usage',
                    **data,
                },
                validate=True,
            )

    @staticmethod
    def usage(name: str, status: str = 'Included', current: int = 0) -> dict:
        return {
            'name': {'value': name, 'localizedValue': name},
            'status': status,
            'currentValue': current,
            'limit': 50,
            'unit': 'Count',
            'quotaPeriod': 'Monthly',
            'nextResetTime': '2026-11-01T00:00:00Z',
        }

    @staticmethod
    def response(payload: dict, status: int = 200) -> requests.Response:
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(payload).encode()
        return response

    def fake_session(self) -> Session:
        session = Session()
        session.credentials = SimpleNamespace(
            get_token=lambda scope: SimpleNamespace(token='test-token'),
        )
        return session

    def test_enumerate_pages_preserves_fields_and_account_identity(self) -> None:
        manager = self.load_usage_policy().resource_manager
        next_url = 'https://management.azure.com/usage-next-page?skiptoken=two'
        responses = [
            self.response(
                {
                    'value': [self.usage('ProvisionedCapacity', 'InOverage', 60)],
                    'nextLink': next_url,
                }
            ),
            self.response({'value': [self.usage('Transactions')]}),
            self.response({'value': [self.usage('ProvisionedCapacity')]}),
        ]
        other_parent = {**self.parent, 'id': self.parent['id'] + '-two'}
        with (
            mock.patch.object(manager, 'get_session', return_value=self.fake_session()),
            mock.patch('requests.Session.get', side_effect=responses) as get,
        ):
            rows = manager.enumerate_resources(self.parent, manager.resource_type)
            other_rows = manager.enumerate_resources(other_parent, manager.resource_type)
        self.assertEqual(
            [r['name']['value'] for r in rows], ['ProvisionedCapacity', 'Transactions']
        )
        self.assertEqual(rows[0]['status'], 'InOverage')
        self.assertEqual(rows[0]['currentValue'], 60)
        self.assertEqual(rows[0]['limit'], 50)
        self.assertNotEqual(
            rows[0][manager.resource_type.id], other_rows[0][manager.resource_type.id]
        )
        self.assertNotIn('id', rows[0])
        self.assertEqual(
            get.call_args_list[0].args[0],
            'https://management.azure.com/subscriptions/test/resourceGroups/'
            'usage-test/providers/Microsoft.CognitiveServices/accounts/'
            'account-one/usages',
        )
        self.assertEqual(get.call_args_list[0].kwargs['params'], {'api-version': '2025-06-01'})
        self.assertEqual(get.call_args_list[1].args[0], next_url)
        self.assertIsNone(get.call_args_list[1].kwargs['params'])

    def test_policy_selects_metric_status_and_usage(self) -> None:
        policy = self.load_usage_policy(
            filters=[
                {'type': 'value', 'key': 'name.value', 'op': 'contains', 'value': 'Provisioned'},
                {'type': 'value', 'key': 'status', 'op': 'in', 'value': ['InOverage', 'Blocked']},
                {'type': 'value', 'key': 'currentValue', 'op': 'gt', 'value': 50},
            ]
        )
        manager = policy.resource_manager
        with (
            mock.patch.object(
                manager.get_parent_manager(), 'resources', return_value=[self.parent]
            ),
            mock.patch.object(manager, 'get_session', return_value=self.fake_session()),
            mock.patch(
                'requests.Session.get',
                return_value=self.response(
                    {
                        'value': [
                            self.usage('ProvisionedCapacity', 'InOverage', 60),
                            self.usage('ProvisionedThroughput', 'Blocked', 70),
                            self.usage('ProvisionedTokens', 'Included', 60),
                            self.usage('ProvisionedUnits', 'Blocked', 40),
                            self.usage('Transactions', 'Blocked', 70),
                        ]
                    }
                ),
            ),
        ):
            rows = policy.run()
        self.assertEqual(
            [row['name']['value'] for row in rows],
            ['ProvisionedCapacity', 'ProvisionedThroughput'],
        )
        self.assertEqual(rows[0]['c7n:parent-id'], self.parent['id'])

    def test_permanent_http_failure_is_not_retried(self) -> None:
        manager = self.load_usage_policy().resource_manager
        with (
            mock.patch.object(manager, 'get_session', return_value=self.fake_session()),
            mock.patch(
                'urllib3.connectionpool.HTTPSConnectionPool._make_request',
                return_value=self.transport_response({'error': {}}, 403),
            ) as send,
        ):
            with self.assertRaises(requests.HTTPError) as error:
                manager.enumerate_resources(self.parent, manager.resource_type)
        self.assertEqual(error.exception.response.status_code, 403)
        self.assertEqual(send.call_count, 1)

    def test_missing_value_is_not_an_empty_result(self) -> None:
        manager = self.load_usage_policy().resource_manager
        with (
            mock.patch.object(manager, 'get_session', return_value=self.fake_session()),
            mock.patch('requests.Session.get', return_value=self.response({})),
        ):
            with self.assertRaises(KeyError):
                manager.enumerate_resources(self.parent, manager.resource_type)

    def test_empty_usages(self) -> None:
        manager = self.load_usage_policy().resource_manager
        with (
            mock.patch.object(manager, 'get_session', return_value=self.fake_session()),
            mock.patch(
                'requests.Session.get',
                return_value=self.response({'value': []}),
            ),
        ):
            self.assertEqual(manager.enumerate_resources(self.parent, manager.resource_type), [])

    @staticmethod
    def transport_response(payload: dict, status: int = 200) -> urllib3.HTTPResponse:
        return urllib3.HTTPResponse(
            body=io.BytesIO(json.dumps(payload).encode()),
            status=status,
            headers={'Content-Type': 'application/json', 'Retry-After': '0'},
            preload_content=False,
        )

    def test_enumerates_with_uninitialized_credentials(self) -> None:
        manager = self.load_usage_policy().resource_manager
        session = Session()
        self.assertIsNone(session.credentials)
        with (
            mock.patch.object(manager, 'get_session', return_value=session),
            mock.patch(
                'c7n_azure.session.AzureCredential', return_value=self.fake_session().credentials
            ),
            mock.patch(
                'urllib3.connectionpool.HTTPSConnectionPool._make_request',
                return_value=self.transport_response(
                    {
                        'value': [self.usage('Transactions')],
                    }
                ),
            ) as send,
        ):
            rows = manager.enumerate_resources(self.parent, manager.resource_type)
        self.assertEqual([row['name']['value'] for row in rows], ['Transactions'])
        self.assertEqual(send.call_args.kwargs['headers']['Authorization'], 'Bearer test-token')

    def test_retries_transient_errors_across_pages(self) -> None:
        manager = self.load_usage_policy().resource_manager
        with (
            mock.patch.object(manager, 'get_session', return_value=self.fake_session()),
            mock.patch(
                'urllib3.connectionpool.HTTPSConnectionPool._make_request',
                side_effect=[
                    self.transport_response({'error': {}}, 429),
                    self.transport_response(
                        {
                            'value': [self.usage('Transactions')],
                            'nextLink': 'https://management.azure.com/usage-next-page',
                        }
                    ),
                    self.transport_response({'error': {}}, 503),
                    self.transport_response(
                        {
                            'value': [self.usage('ProvisionedCapacity')],
                        }
                    ),
                ],
            ) as send,
        ):
            rows = manager.enumerate_resources(self.parent, manager.resource_type)
        self.assertEqual(
            [row['name']['value'] for row in rows],
            ['Transactions', 'ProvisionedCapacity'],
        )
        self.assertEqual(send.call_count, 4)

    def test_retry_exhaustion_raises_http_error(self) -> None:
        manager = self.load_usage_policy().resource_manager
        for status in (429, 503):
            with (
                self.subTest(status=status),
                mock.patch.object(manager, 'get_session', return_value=self.fake_session()),
                mock.patch(
                    'urllib3.connectionpool.HTTPSConnectionPool._make_request',
                    side_effect=[self.transport_response({'error': {}}, status) for _ in range(4)],
                ) as send,
            ):
                with self.assertRaises(requests.HTTPError) as error:
                    manager.enumerate_resources(self.parent, manager.resource_type)
                self.assertEqual(error.exception.response.status_code, status)
                self.assertEqual(send.call_count, 4)

    def test_arm_actions_are_not_available(self) -> None:
        self.load_usage_policy()
        for action in ('delete', 'tag', 'lock'):
            with self.subTest(action=action), self.assertRaises(PolicyValidationError):
                self.load_usage_policy(actions=[{'type': action}])


class CognitiveServiceUsageTest(BaseTest):
    recording_resource_group = 'test_cognitive-service-usage'

    @arm_template('cognitive-service-usage.json')
    def test_usage_fields_and_parent(self) -> None:
        policy = self.load_policy(
            {
                'name': 'cognitiveservice-usage-fields',
                'resource': 'azure.cognitiveservice-usage',
                'filters': [
                    {
                        'type': 'value',
                        'key': 'name.value',
                        'op': 'contains',
                        'value': 'TextAnalytics.',
                    },
                    {'type': 'value', 'key': 'status', 'value': 'Included'},
                    {'type': 'value', 'key': 'currentValue', 'op': 'ge', 'value': 0},
                    {
                        'type': 'parent',
                        'filter': {'resourceGroup': self.recording_resource_group},
                    },
                ],
            },
        )
        parent = policy.resource_manager.get_parent_manager()
        parent.filters.append(
            parent.filter_registry.factory(
                {'resourceGroup': self.recording_resource_group},
                parent,
            )
        )
        rows = policy.run()
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertIsInstance(row['name']['value'], str)
            self.assertIsInstance(row['currentValue'], (int, float))
            self.assertIsInstance(row['limit'], (int, float))
            self.assertEqual(row['status'], 'Included')
            self.assertIn(
                '/resourcegroups/test_cognitive-service-usage/',
                row['c7n:parent-id'].lower(),
            )
        self.assertEqual(len({row['c7n:usage-id'] for row in rows}), len(rows))
        negative_filter = policy.resource_manager.filter_registry.factory(
            {'type': 'value', 'key': 'currentValue', 'op': 'lt', 'value': 0},
            policy.resource_manager,
        )
        self.assertEqual(negative_filter.process(rows), [])
