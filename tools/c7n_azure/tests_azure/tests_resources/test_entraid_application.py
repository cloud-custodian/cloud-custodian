# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import requests

from c7n.exceptions import PolicyValidationError
from c7n_azure.graph_utils import get_required_permissions_for_endpoint
from c7n_azure.resources.entraid_application import (
    EntraIDApplication,
    EntraIDServicePrincipal,
)
from tests_azure.azure_common import BaseTest

APP_REQUEST = 'c7n_azure.resources.entraid_application.EntraIDApplication.make_graph_request'
SP_REQUEST = (
    'c7n_azure.resources.entraid_application.EntraIDServicePrincipal.make_graph_request'
)


def _iso(days):
    """An ISO 8601 UTC timestamp ``days`` days from now, in Graph's format."""
    moment = datetime.now(timezone.utc) + timedelta(days=days)
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


def _app(app_id, password_days=(), key_days=()):
    return {
        'id': app_id,
        'appId': f'{app_id}-client',
        'displayName': f'App {app_id}',
        'createdDateTime': '2024-01-01T00:00:00Z',
        'passwordCredentials': [
            {
                'keyId': f'{app_id}-secret-{index}',
                'displayName': f'secret {index}',
                'endDateTime': _iso(days),
            }
            for index, days in enumerate(password_days)
        ],
        'keyCredentials': [
            {
                'keyId': f'{app_id}-cert-{index}',
                'displayName': f'CN=cert {index}',
                'endDateTime': _iso(days),
                'type': 'AsymmetricX509Cert',
            }
            for index, days in enumerate(key_days)
        ],
    }


def _http_error(status, message=None):
    response = requests.models.Response()
    response.status_code = status
    return requests.exceptions.HTTPError(message or f'{status} Error', response=response)


class EntraIDApplicationTest(BaseTest):

    def test_schema_validate(self):
        with self.sign_out_patch():
            for resource in ('azure.entraid-application', 'azure.entraid-service-principal'):
                p = self.load_policy({
                    'name': 'test-credential-expiration',
                    'resource': resource,
                    'filters': [{
                        'type': 'credential-expiration',
                        'days': 30,
                        'credential-type': 'password',
                        'include-expired': False,
                    }]
                }, validate=True)
                self.assertTrue(p)

    def test_schema_requires_days(self):
        with self.sign_out_patch():
            with self.assertRaises(PolicyValidationError):
                self.load_policy({
                    'name': 'test-missing-days',
                    'resource': 'azure.entraid-application',
                    'filters': [{'type': 'credential-expiration'}]
                }, validate=True)

    def test_resource_types(self):
        for manager, collection in (
            (EntraIDApplication, 'applications'),
            (EntraIDServicePrincipal, 'servicePrincipals'),
        ):
            resource_type = manager.resource_type
            self.assertEqual(resource_type.service, 'graph')
            self.assertEqual(resource_type.id, 'id')
            self.assertEqual(resource_type.name, 'displayName')
            self.assertTrue(resource_type.global_resource)
            self.assertEqual(resource_type.permissions, ('Application.Read.All',))
            self.assertEqual(manager.collection, collection)

    def test_endpoint_permissions_are_mapped(self):
        self.assertEqual(
            get_required_permissions_for_endpoint('applications?$top=999'),
            ['Application.Read.All'])
        self.assertEqual(
            get_required_permissions_for_endpoint(
                'servicePrincipals?$top=999&$skiptoken=RFNwdAIAAQAAAB'),
            ['Application.Read.All'])

    @patch(APP_REQUEST)
    def test_get_resources_follows_next_link(self, mock_request):
        mock_request.side_effect = [
            {
                'value': [_app('a1')],
                '@odata.nextLink':
                    'https://graph.microsoft.com/v1.0/applications?$top=999&$skiptoken=abc',
            },
            {'value': [_app('a2')]},
        ]
        p = self.load_policy({'name': 'apps', 'resource': 'azure.entraid-application'})
        resources = p.resource_manager.get_graph_resources()

        self.assertEqual([r['id'] for r in resources], ['a1', 'a2'])
        self.assertEqual(
            [c.args[0] for c in mock_request.call_args_list],
            ['applications?$top=999',
             'https://graph.microsoft.com/v1.0/applications?$top=999&$skiptoken=abc'])

    @patch(SP_REQUEST)
    def test_service_principal_endpoint(self, mock_request):
        mock_request.return_value = {'value': [_app('sp1')]}
        p = self.load_policy({
            'name': 'sps', 'resource': 'azure.entraid-service-principal'})
        resources = p.resource_manager.get_graph_resources()

        self.assertEqual(len(resources), 1)
        mock_request.assert_called_once_with('servicePrincipals?$top=999')

    @patch(APP_REQUEST)
    def test_permission_error_is_raised(self, mock_request):
        mock_request.side_effect = _http_error(403)
        p = self.load_policy({'name': 'apps', 'resource': 'azure.entraid-application'})
        with self.assertLogs('custodian.azure.entraid.application', 'ERROR') as logs:
            with self.assertRaises(requests.exceptions.HTTPError):
                p.run()
        self.assertTrue(any('Application.Read.All' in line for line in logs.output))

    @patch(APP_REQUEST)
    def test_server_error_on_second_page_is_raised(self, mock_request):
        mock_request.side_effect = [
            {
                'value': [_app('a1')],
                '@odata.nextLink':
                    'https://graph.microsoft.com/v1.0/applications?$top=999&$skiptoken=abc',
            },
            _http_error(500),
        ]
        p = self.load_policy({
            'name': 'expiring',
            'resource': 'azure.entraid-application',
            'filters': [{'type': 'credential-expiration', 'days': 30}],
        })
        with self.assertRaises(requests.exceptions.HTTPError):
            p.run()

    @patch(APP_REQUEST)
    def test_403_text_in_message_is_not_a_permission_error(self, mock_request):
        # The status code decides, not "403" appearing in an id or $skiptoken
        mock_request.side_effect = _http_error(
            500, 'Server error for url: ...$skiptoken=X403Y')
        p = self.load_policy({'name': 'apps', 'resource': 'azure.entraid-application'})
        with patch('c7n_azure.resources.entraid_application.log') as mock_log:
            with self.assertRaises(requests.exceptions.HTTPError):
                p.resource_manager.get_graph_resources()
        mock_log.error.assert_not_called()

    @patch('c7n_azure.graph_utils.requests.get')
    def test_make_graph_request_accepts_absolute_url(self, mock_get):
        mock_get.return_value.json.return_value = {'value': []}
        p = self.load_policy({'name': 'apps', 'resource': 'azure.entraid-application'})
        manager = p.resource_manager
        session = MagicMock()
        session.credentials.get_token.return_value.token = 'token'
        with patch.object(manager, 'get_client', return_value=session):
            next_link = 'https://graph.microsoft.com/v1.0/applications?$skiptoken=abc'
            manager.make_graph_request(next_link)
            manager.make_graph_request('applications?$top=999')
        self.assertEqual(
            [c.args[0] for c in mock_get.call_args_list],
            [next_link, 'https://graph.microsoft.com/v1.0/applications?$top=999'])

    @patch(APP_REQUEST)
    def test_policy_run_reports_expiring_credentials(self, mock_request):
        mock_request.return_value = {'value': [
            _app('soon', password_days=[10, 400]),
            _app('later', password_days=[90], key_days=[200]),
            _app('none'),
        ]}
        p = self.load_policy({
            'name': 'expiring',
            'resource': 'azure.entraid-application',
            'filters': [{'type': 'credential-expiration', 'days': 30}],
        })
        resources = p.run()

        self.assertEqual([r['id'] for r in resources], ['soon'])
        annotation = resources[0]['c7n:ExpiringCredentials']
        self.assertEqual(len(annotation), 1)
        self.assertEqual(annotation[0]['type'], 'password')
        self.assertEqual(annotation[0]['keyId'], 'soon-secret-0')
        self.assertEqual(annotation[0]['displayName'], 'secret 0')
        self.assertIn(annotation[0]['daysRemaining'], (9, 10))


class CredentialExpirationFilterTest(BaseTest):

    def _filter(self, resources, **data):
        data.update({'type': 'credential-expiration'})
        p = self.load_policy({
            'name': 'credential-expiration',
            'resource': 'azure.entraid-application',
            'filters': [data],
        })
        return p.resource_manager.filters[0].process(resources)

    def test_expired_credentials_included_by_default(self):
        resources = self._filter([_app('old', password_days=[-5])], days=30)
        self.assertEqual(len(resources), 1)
        self.assertLess(resources[0]['c7n:ExpiringCredentials'][0]['daysRemaining'], 0)

    def test_exclude_expired(self):
        resources = self._filter(
            [_app('old', password_days=[-5]), _app('soon', password_days=[5])],
            days=30, **{'include-expired': False})
        self.assertEqual([r['id'] for r in resources], ['soon'])

    def test_days_zero_matches_only_expired(self):
        resources = self._filter(
            [_app('old', key_days=[-1]), _app('soon', key_days=[1])], days=0)
        self.assertEqual([r['id'] for r in resources], ['old'])

    def test_credential_type_password(self):
        resources = self._filter(
            [_app('cert-only', key_days=[5]), _app('secret', password_days=[5])],
            days=30, **{'credential-type': 'password'})
        self.assertEqual([r['id'] for r in resources], ['secret'])

    def test_credential_type_key(self):
        resources = self._filter(
            [_app('cert-only', key_days=[5]), _app('secret', password_days=[5])],
            days=30, **{'credential-type': 'key'})
        self.assertEqual([r['id'] for r in resources], ['cert-only'])
        self.assertEqual(resources[0]['c7n:ExpiringCredentials'][0]['type'], 'key')

    def test_all_types_annotated_together(self):
        resources = self._filter([_app('both', password_days=[3], key_days=[4])], days=30)
        types = sorted(c['type'] for c in resources[0]['c7n:ExpiringCredentials'])
        self.assertEqual(types, ['key', 'password'])

    def test_missing_or_unparseable_dates_are_skipped(self):
        app = _app('odd')
        app['passwordCredentials'] = [
            {'keyId': 'no-end'},
            {'keyId': 'empty', 'endDateTime': ''},
            {'keyId': 'bad', 'endDateTime': 'not-a-date'},
        ]
        app['keyCredentials'] = None
        with self.assertLogs('custodian.azure.entraid.application', 'WARNING') as logs:
            self.assertEqual(self._filter([app], days=3650), [])
        self.assertTrue(any('odd' in line and 'keyId bad' in line for line in logs.output))

    def test_fractional_seconds_and_naive_dates(self):
        soon = datetime.now(timezone.utc) + timedelta(days=2)
        app = _app('formats')
        app['passwordCredentials'] = [
            {'keyId': 'fractional', 'endDateTime': soon.strftime('%Y-%m-%dT%H:%M:%S.1234567Z')},
            {'keyId': 'naive', 'endDateTime': soon.strftime('%Y-%m-%dT%H:%M:%S')},
        ]
        resources = self._filter([app], days=7)
        self.assertEqual(
            [c['keyId'] for c in resources[0]['c7n:ExpiringCredentials']],
            ['fractional', 'naive'])
