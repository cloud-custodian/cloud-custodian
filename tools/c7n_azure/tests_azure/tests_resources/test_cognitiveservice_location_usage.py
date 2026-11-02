# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
from collections import Counter
from types import SimpleNamespace
from unittest import mock

import requests

import c7n.policy

from c7n.exceptions import PolicyValidationError
from c7n_azure.resources.ai_foundry import CognitiveService
from c7n_azure.session import Session

from ..azure_common import BaseTest, arm_template


class CognitiveServiceLocationUsageUnitTest(BaseTest):

    def load_usage_policy(self, **data: object) -> c7n.policy.Policy:
        with self.sign_out_patch():
            return self.load_policy(
                {
                    'name': 'test-cognitiveservice-location-usage',
                    'resource': 'azure.cognitiveservice-location-usage',
                    **data,
                },
                validate=True,
            )

    @staticmethod
    def response(payload: dict) -> requests.Response:
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(payload).encode()
        return response

    def fake_session(self) -> Session:
        session = Session()
        session.credentials = SimpleNamespace(
            get_token=lambda scope: SimpleNamespace(token='test-token'),
            subscription_id='test',
        )
        return session

    def test_enumerate_pages_with_api_version(self) -> None:
        # The cassette matcher ignores api-version, and recorded usages fit one page.
        manager = self.load_usage_policy().resource_manager
        next_url = 'https://management.azure.com/usage-next-page?skiptoken=two'
        responses = [
            self.response(
                {
                    'value': [{'name': {'value': 'AccountCount'}}],
                    'nextLink': next_url,
                }
            ),
            self.response({'value': [{'name': {'value': 'OpenAI.ProvisionedManaged'}}]}),
        ]
        with (
            mock.patch.object(
                CognitiveService, 'resources', return_value=[{'location': 'eastus'}]
            ),
            mock.patch.object(manager, 'get_session', return_value=self.fake_session()),
            mock.patch('requests.Session.get', side_effect=responses) as get,
        ):
            rows = manager.source.get_resources(None)
        self.assertEqual(
            [r['name']['value'] for r in rows], ['AccountCount', 'OpenAI.ProvisionedManaged']
        )
        self.assertEqual(get.call_args_list[0].kwargs['params'], {'api-version': '2026-03-01'})
        self.assertEqual(get.call_args_list[1].args[0], next_url)
        self.assertIsNone(get.call_args_list[1].kwargs['params'])

    def test_arm_actions_are_not_available(self) -> None:
        self.load_usage_policy()
        for action in ('delete', 'tag', 'lock'):
            with self.subTest(action=action), self.assertRaises(PolicyValidationError):
                self.load_usage_policy(actions=[{'type': action}])


class CognitiveServiceLocationUsageTest(BaseTest):
    recording_resource_group = 'test_cognitive-service-location-usage'

    @arm_template('cognitive-service-location-usage.json')
    def test_location_usage_rows(self) -> None:
        policy = self.load_policy(
            {
                'name': 'cognitiveservice-location-usage',
                'resource': 'azure.cognitiveservice-location-usage',
            },
        )
        rows = policy.run()

        names = Counter(
            (row.get('scopeType'), row['name']['value']) for row in rows
        )
        # Shared quota is listed once, regional quota once per location.
        self.assertEqual(names[('DataZone', 'OpenAI.DataZoneProvisionedManaged')], 1)
        self.assertEqual(names[('Classic', 'OpenAI.ProvisionedManaged')], 2)
        self.assertEqual(
            sorted(row['c7n:location'] for row in rows if row['name']['value'] == 'AccountCount'),
            ['global', 'westus', 'westus3'],
        )
        # The global location returns this row as Classic; the regions' Global row wins.
        self.assertEqual(names[('Global', 'OpenAI.GlobalProvisionedManaged')], 1)
        self.assertEqual(names[('Classic', 'OpenAI.GlobalProvisionedManaged')], 0)
        global_row = next(
            row for row in rows if row['name']['value'] == 'OpenAI.GlobalProvisionedManaged'
        )
        self.assertEqual(global_row['c7n:location'], 'westus')
