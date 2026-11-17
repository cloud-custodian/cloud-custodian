# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

from ..azure_common import BaseTest, arm_template, cassette_name
from c7n_azure.session import Session

from c7n.utils import local_session


class WebAppTest(BaseTest):
    def setUp(self):
        super(WebAppTest, self).setUp()

    def test_validate_webapp_schema(self):
        with self.sign_out_patch():

            p = self.load_policy({
                'name': 'test-azure-webapp',
                'resource': 'azure.webapp'
            }, validate=True)

            self.assertTrue(p)

    def test_validate_webapp_action_schemas(self):
        with self.sign_out_patch():

            p = self.load_policy({
                'name': 'test-azure-webapp',
                'resource': 'azure.webapp',
                'actions': [
                    {'type': 'stop'},
                    {'type': 'start'},
                ]
            }, validate=True)

            self.assertTrue(p)

    @arm_template('webapp.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-webapp',
            'resource': 'azure.webapp',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestwebapp*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('webapp.json')
    def test_find_by_min_tls(self):
        # webapp.json deploys a webapp with minTlsVerion='1.0'
        p = self.load_policy({
            'name': 'test-azure-webapp',
            'resource': 'azure.webapp',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctestwebapp*'},
                {
                    'type': 'configuration',
                    'key': 'minTlsVersion',
                    'value': '1.2',
                    'op': 'ne'
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('webapp.json')
    def test_find_by_auth_disabled(self):
        # webapp.json deploys a webapp without authentication
        p = self.load_policy({
            'name': 'test-azure-webapp',
            'resource': 'azure.webapp',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctestwebapp*'},
                {
                    'type': 'authentication',
                    'key': 'enabled',
                    'value': False,
                    'op': 'eq'
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('webapp.json')
    @cassette_name('test_find_by_name')
    def test_stop(self):
        with patch(self._get_webapp_client_string() + '.stop') as stop_action_mock:
            p = self.load_policy({
                'name': 'test-azure-webapp',
                'resource': 'azure.webapp',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'glob',
                     'value_type': 'normalize',
                     'value': 'cctestwebapp*'}],
                'actions': [
                    {'type': 'stop'}
                ]
            })
            resources = p.run()
            self.assertEqual(len(resources), 1)
            stop_action_mock.assert_called_with(
                resources[0]['resourceGroup'],
                resources[0]['name'])

    @arm_template('webapp.json')
    @cassette_name('test_find_by_name')
    def test_start(self):
        with patch(self._get_webapp_client_string() + '.start') as start_action_mock:
            p = self.load_policy({
                'name': 'test-azure-webapp',
                'resource': 'azure.webapp',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'glob',
                     'value_type': 'normalize',
                     'value': 'cctestwebapp*'}],
                'actions': [
                    {'type': 'start'}
                ]
            })
            resources = p.run()
            self.assertEqual(len(resources), 1)
            start_action_mock.assert_called_with(
                resources[0]['resourceGroup'],
                resources[0]['name'])

    def _get_webapp_client_string(self):
        client = local_session(Session)\
            .client('azure.mgmt.web.WebSiteManagementClient').web_apps
        return client.__module__ + '.' + client.__class__.__name__
