# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import requests
from unittest.mock import Mock, patch

from c7n_azure.graph_utils import (
    GraphSource, get_required_permissions_for_endpoint,
    GraphResourceManager, GraphTypeInfo, EntraIDDiagnosticSettingsFilter
)
from c7n_azure.constants import MSGRAPH_RESOURCE_ID
from tests_azure.azure_common import BaseTest

# Ensure entraid resources are loaded for tests


class TestGraphSource(BaseTest):
    """Test GraphSource functionality"""

    def test_graph_source_init(self):
        """Test GraphSource initialization"""
        mock_manager = Mock()
        source = GraphSource(mock_manager)
        self.assertEqual(source.manager, mock_manager)

    def test_get_resources_success(self):
        """Test successful resource retrieval via GraphSource"""
        mock_manager = Mock()
        mock_manager.get_graph_resources.return_value = [
            {'id': 'test1', 'name': 'Resource 1'},
            {'id': 'test2', 'name': 'Resource 2'}
        ]

        source = GraphSource(mock_manager)
        resources = source.get_resources()

        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['id'], 'test1')
        mock_manager.get_graph_resources.assert_called_once()

    def test_get_resources_exception_handling(self):
        """Test GraphSource exception handling in get_resources"""
        mock_manager = Mock()
        mock_manager.get_graph_resources.side_effect = Exception("Graph API error")

        source = GraphSource(mock_manager)
        with patch('c7n_azure.graph_utils.log') as mock_log:
            resources = source.get_resources()

        # Should return empty list on error
        self.assertEqual(resources, [])
        mock_log.error.assert_called_once_with(
            "Error retrieving resources via Graph API: Graph API error"
        )


class TestGetRequiredPermissions(BaseTest):
    """Test get_required_permissions_for_endpoint function"""

    def test_exact_endpoint_match(self):
        """Test exact endpoint matching"""
        permissions = get_required_permissions_for_endpoint('users')
        self.assertEqual(permissions, ['User.Read.All'])

        permissions = get_required_permissions_for_endpoint('groups')
        self.assertEqual(permissions, ['Group.Read.All'])

    def test_endpoint_with_id_normalization(self):
        """Test endpoint normalization with IDs"""
        # UUID should be normalized to {id}
        permissions = get_required_permissions_for_endpoint(
            'users/12345678-1234-1234-1234-123456789abc'
        )
        self.assertEqual(permissions, ['User.Read.All'])

        # Short UUID should also be normalized
        permissions = get_required_permissions_for_endpoint('users/12345678-abcd')
        self.assertEqual(permissions, ['User.Read.All'])

    def test_write_operations_users(self):
        """Test write operations for user endpoints"""
        for method in ['PATCH', 'POST', 'PUT', 'DELETE']:
            permissions = get_required_permissions_for_endpoint('users/test-id', method)
            self.assertEqual(permissions, ['User.ReadWrite.All'])

    def test_write_operations_groups(self):
        """Test write operations for group endpoints"""
        for method in ['PATCH', 'POST', 'PUT', 'DELETE']:
            permissions = get_required_permissions_for_endpoint('groups/test-id', method)
            self.assertEqual(permissions, ['Group.ReadWrite.All'])

    def test_write_operations_authentication(self):
        """Test write operations for authentication endpoints"""
        # Note: Due to current implementation, 'users' pattern matches first
        # even for authentication endpoints in write operations
        for method in ['PATCH', 'POST', 'PUT', 'DELETE']:
            permissions = get_required_permissions_for_endpoint(
                'users/test-id/authentication/methods', method
            )
            self.assertEqual(permissions, ['User.ReadWrite.All'])  # 'users' matches first

    def test_pattern_matching(self):
        """Test pattern matching for complex endpoints"""
        # With exact match first, should get specific permissions
        permissions = get_required_permissions_for_endpoint(
            'users/12345678-1234-1234-1234-123456789abc/authentication/methods'
        )
        self.assertEqual(permissions, ['UserAuthenticationMethod.Read.All'])

        permissions = get_required_permissions_for_endpoint(
            'users/12345678-1234-1234-1234-123456789abc/transitiveMemberOf'
        )
        self.assertEqual(permissions, ['GroupMember.Read.All'])

        # Test fallback pattern matching when no exact match
        # This endpoint doesn't have exact match so should fallback to 'users' pattern
        permissions = get_required_permissions_for_endpoint(
            'users/12345678-1234-1234-1234-123456789abc/someUnmappedSubpath'
        )
        self.assertEqual(permissions, ['User.Read.All'])

    def test_unmapped_endpoint_raises_error(self):
        """Test that unmapped endpoints raise ValueError"""
        with patch('c7n_azure.graph_utils.log') as mock_log:
            with self.assertRaises(ValueError) as context:
                get_required_permissions_for_endpoint('unknown/endpoint')

            self.assertIn("Unmapped Graph API endpoint", str(context.exception))
            mock_log.error.assert_called_once()


class TestGraphResourceManager(BaseTest):
    """Test GraphResourceManager base class"""

    def test_get_client(self):
        """Test GraphResourceManager get_client method"""
        # Create a proper policy to get a real manager instance
        policy = self.load_policy({
            'name': 'test-graph-manager',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        manager.session_factory = Mock()

        mock_session = Mock()
        mock_graph_session = Mock()
        mock_session.get_session_for_resource.return_value = mock_graph_session

        with patch('c7n_azure.graph_utils.local_session', return_value=mock_session):
            client = manager.get_client()

        mock_session.get_session_for_resource.assert_called_once_with(MSGRAPH_RESOURCE_ID)
        self.assertEqual(client, mock_graph_session)

    def test_make_graph_request_success(self):
        """Test successful Graph API request"""
        policy = self.load_policy({
            'name': 'test-graph-request',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = Mock()
        mock_token = Mock()
        mock_token.token = 'fake-token'
        mock_session.credentials.get_token.return_value = mock_token

        mock_response = Mock()
        mock_response.json.return_value = {'test': 'data'}

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get', return_value=mock_response):
                    result = manager.make_graph_request('users')

        self.assertEqual(result, {'test': 'data'})
        mock_response.raise_for_status.assert_called_once()

    def test_make_graph_request_permission_check_error(self):
        """Test make_graph_request with permission check error"""
        policy = self.load_policy({
            'name': 'test-permission-error',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager

        with patch.object(manager, 'get_client'):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint',
                      side_effect=ValueError("Unmapped endpoint")):
                with self.assertRaises(ValueError):
                    manager.make_graph_request('unmapped/endpoint')

    def test_make_graph_request_api_error(self):
        """Test make_graph_request with API request error"""
        policy = self.load_policy({
            'name': 'test-api-error',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = Mock()

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get',
                          side_effect=requests.exceptions.RequestException("API Error")):
                    with self.assertRaises(requests.exceptions.RequestException):
                        manager.make_graph_request('users')

    def test_register_graph_specific_non_graph_resource(self):
        """Test register_graph_specific with non-Graph resource"""
        mock_registry = Mock()
        mock_non_graph_class = Mock()

        # Mock issubclass to return False (not a GraphResourceManager)
        with patch('c7n_azure.graph_utils.issubclass', return_value=False):
            GraphResourceManager.register_graph_specific(mock_registry, mock_non_graph_class)

        # Should return early and not register anything
        mock_non_graph_class.filter_registry.register.assert_not_called()

    def _setup_mock_session(self, token='fake-token'):
        """Helper method to set up mock session for tests"""
        mock_session = Mock()
        mock_token = Mock()
        mock_token.token = token
        mock_session.credentials.get_token.return_value = mock_token
        # Ensure _initialize_session doesn't raise an exception
        mock_session._initialize_session.return_value = None
        return mock_session

    def test_base_make_graph_request_success(self):
        """Test successful Graph API request using base GraphResourceManager class"""
        from c7n_azure.graph_utils import GraphResourceManager
        from unittest.mock import MagicMock

        # Create a minimal context object
        ctx = MagicMock()
        ctx.session_factory = MagicMock()

        # Create GraphResourceManager instance directly
        manager = GraphResourceManager(ctx, {})

        mock_session = self._setup_mock_session()
        mock_response = Mock()
        mock_response.json.return_value = {'test': 'data'}

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get', return_value=mock_response):
                    result = manager.make_graph_request('users')

        self.assertEqual(result, {'test': 'data'})
        mock_response.raise_for_status.assert_called_once()

    def test_base_make_graph_request_permission_error(self):
        """Test permission error in base class"""
        from c7n_azure.graph_utils import GraphResourceManager
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.session_factory = MagicMock()
        manager = GraphResourceManager(ctx, {})

        mock_session = self._setup_mock_session()

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint',
                      side_effect=ValueError("Unmapped endpoint")):
                with patch('c7n_azure.graph_utils.log') as mock_log:
                    with self.assertRaises(ValueError):
                        manager.make_graph_request('unmapped/endpoint')

                    mock_log.error.assert_called_once()

    def test_base_make_graph_request_request_exception(self):
        """Test request exception in base class"""
        from c7n_azure.graph_utils import GraphResourceManager
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.session_factory = MagicMock()
        manager = GraphResourceManager(ctx, {})

        mock_session = self._setup_mock_session()

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get',
                          side_effect=requests.exceptions.RequestException("API Error")):
                    with patch('c7n_azure.graph_utils.log') as mock_log:
                        with self.assertRaises(requests.exceptions.RequestException):
                            manager.make_graph_request('users')

                        mock_log.error.assert_called_once()

    def test_make_graph_request_session_initialization_failure(self):
        """Test session initialization failure"""
        policy = self.load_policy({
            'name': 'test-session-init-fail',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = Mock()
        mock_session._initialize_session.side_effect = Exception("Session init failed")

        with patch.object(manager, 'get_client', return_value=mock_session):
            with self.assertRaises(Exception) as context:
                manager.make_graph_request('users')

            self.assertIn("Session init failed", str(context.exception))

    def test_make_graph_request_token_acquisition_failure(self):
        """Test token acquisition failure"""
        policy = self.load_policy({
            'name': 'test-token-fail',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = Mock()
        mock_session.credentials.get_token.side_effect = Exception("Token acquisition failed")

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with self.assertRaises(Exception) as context:
                    manager.make_graph_request('users')

                self.assertIn("Token acquisition failed", str(context.exception))

    def test_make_graph_request_http_400_error(self):
        """Test HTTP 400 Bad Request error"""
        policy = self.load_policy({
            'name': 'test-400-error',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = self._setup_mock_session()

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = \
            requests.exceptions.HTTPError("400 Bad Request")

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get', return_value=mock_response):
                    with patch('c7n_azure.graph_utils.log') as mock_log:
                        with self.assertRaises(requests.exceptions.HTTPError):
                            manager.make_graph_request('users')

                        mock_log.error.assert_called_once()
                        self.assertIn("400", mock_log.error.call_args[0][0])

    def test_make_graph_request_http_401_error(self):
        """Test HTTP 401 Unauthorized error"""
        policy = self.load_policy({
            'name': 'test-401-error',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = self._setup_mock_session()

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = \
            requests.exceptions.HTTPError("401 Unauthorized")

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get', return_value=mock_response):
                    with self.assertRaises(requests.exceptions.HTTPError):
                        manager.make_graph_request('users')

    def test_make_graph_request_http_403_error(self):
        """Test HTTP 403 Forbidden error"""
        policy = self.load_policy({
            'name': 'test-403-error',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = self._setup_mock_session()

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("403 Forbidden")

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get', return_value=mock_response):
                    with self.assertRaises(requests.exceptions.HTTPError):
                        manager.make_graph_request('users')

    def test_make_graph_request_http_404_error(self):
        """Test HTTP 404 Not Found error"""
        policy = self.load_policy({
            'name': 'test-404-error',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = self._setup_mock_session()

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get', return_value=mock_response):
                    with self.assertRaises(requests.exceptions.HTTPError):
                        manager.make_graph_request('users')

    def test_make_graph_request_timeout(self):
        """Test request timeout handling"""
        policy = self.load_policy({
            'name': 'test-timeout',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = self._setup_mock_session()

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get',
                          side_effect=requests.exceptions.Timeout("Request timed out")):
                    with self.assertRaises(requests.exceptions.Timeout):
                        manager.make_graph_request('users')

    def test_make_graph_request_connection_error(self):
        """Test connection error handling"""
        policy = self.load_policy({
            'name': 'test-connection-error',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = self._setup_mock_session()

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get',
                          side_effect=requests.exceptions.ConnectionError("Connection failed")):
                    with self.assertRaises(requests.exceptions.ConnectionError):
                        manager.make_graph_request('users')

    def test_make_graph_request_invalid_json_response(self):
        """Test invalid JSON response handling"""
        policy = self.load_policy({
            'name': 'test-invalid-json',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = self._setup_mock_session()

        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get', return_value=mock_response):
                    with self.assertRaises(ValueError):
                        manager.make_graph_request('users')

    def test_make_graph_request_empty_response(self):
        """Test empty JSON response"""
        policy = self.load_policy({
            'name': 'test-empty-response',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = self._setup_mock_session()

        mock_response = Mock()
        mock_response.json.return_value = {}

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get', return_value=mock_response):
                    result = manager.make_graph_request('users')

        self.assertEqual(result, {})

    def test_make_graph_request_url_construction(self):
        """Test URL construction with various endpoint formats"""
        policy = self.load_policy({
            'name': 'test-url-construction',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = self._setup_mock_session()

        test_cases = [
            ('users', 'https://graph.microsoft.com/v1.0/users'),
            ('users/123', 'https://graph.microsoft.com/v1.0/users/123'),
            ('groups/456/members', 'https://graph.microsoft.com/v1.0/groups/456/members'),
        ]

        for endpoint, expected_url in test_cases:
            with self.subTest(endpoint=endpoint):
                mock_response = Mock()
                mock_response.json.return_value = {'test': 'data'}

                with patch.object(manager, 'get_client', return_value=mock_session):
                    with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                        with patch('c7n_azure.graph_utils.requests.get',
                                  return_value=mock_response) as mock_get:
                            manager.make_graph_request(endpoint)

                            # Verify correct URL construction
                            args, kwargs = mock_get.call_args
                            self.assertEqual(args[0], expected_url)

    def test_make_graph_request_headers_validation(self):
        """Test that correct headers are set"""
        policy = self.load_policy({
            'name': 'test-headers',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = Mock()
        mock_token = Mock()
        mock_token.token = 'test-bearer-token-123'
        mock_session.credentials.get_token.return_value = mock_token

        mock_response = Mock()
        mock_response.json.return_value = {'test': 'data'}

        expected_headers = {
            'Authorization': 'Bearer test-bearer-token-123',
            'Content-Type': 'application/json'
        }

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get',
                          return_value=mock_response) as mock_get:
                    manager.make_graph_request('users')

                    # Verify headers
                    args, kwargs = mock_get.call_args
                    self.assertEqual(kwargs['headers'], expected_headers)
                    self.assertEqual(kwargs['timeout'], 30)

    def test_make_graph_request_token_scope_validation(self):
        """Test that correct token scope is requested"""
        policy = self.load_policy({
            'name': 'test-token-scope',
            'resource': 'azure.entraid-user'
        })

        manager = policy.resource_manager
        mock_session = Mock()
        mock_token = Mock()
        mock_token.token = 'fake-token'
        mock_session.credentials.get_token.return_value = mock_token

        mock_response = Mock()
        mock_response.json.return_value = {'test': 'data'}

        with patch.object(manager, 'get_client', return_value=mock_session):
            with patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint'):
                with patch('c7n_azure.graph_utils.requests.get', return_value=mock_response):
                    manager.make_graph_request('users')

                    # Verify correct scope is used
                    mock_session.credentials.get_token.assert_called_once_with(
                        'https://graph.microsoft.com/.default'
                    )

    def test_register_graph_specific_with_diagnostic_settings(self):
        """Test register_graph_specific with diagnostic settings enabled"""
        mock_registry = Mock()
        mock_resource_class = Mock()
        mock_resource_class.resource_type.diagnostic_settings_enabled = True

        with patch('c7n_azure.graph_utils.issubclass', return_value=True):
            GraphResourceManager.register_graph_specific(mock_registry, mock_resource_class)

        mock_resource_class.filter_registry.register.assert_called_once_with(
            'diagnostic-settings', EntraIDDiagnosticSettingsFilter
        )

    def test_register_graph_specific_without_diagnostic_settings(self):
        """Test register_graph_specific with diagnostic settings disabled"""
        mock_registry = Mock()
        mock_resource_class = Mock()
        mock_resource_class.resource_type.diagnostic_settings_enabled = False

        with patch('c7n_azure.graph_utils.issubclass', return_value=True):
            GraphResourceManager.register_graph_specific(mock_registry, mock_resource_class)

        mock_resource_class.filter_registry.register.assert_not_called()


class TestGraphTypeInfo(BaseTest):
    """Test GraphTypeInfo class"""

    def test_extra_args(self):
        """Test GraphTypeInfo.extra_args method"""
        result = GraphTypeInfo.extra_args(None)
        self.assertEqual(result, {})


class TestEntraIDDiagnosticSettingsFilter(BaseTest):
    """Test EntraIDDiagnosticSettingsFilter"""

    def test_process_successful_with_settings(self):
        """Test successful diagnostic settings retrieval and filtering"""
        resources = [{'id': 'resource1'}, {'id': 'resource2'}]

        mock_session = Mock()
        mock_credentials = Mock()
        mock_token = Mock()
        mock_token.token = 'fake-token'
        mock_credentials.get_token.return_value = mock_token
        mock_session.get_credentials.return_value = mock_credentials

        mock_response = Mock()
        mock_response.json.return_value = {
            'value': [
                {'id': 'setting1', 'name': 'diagnostic1'}
            ]
        }

        # Create properly mocked filter instance
        filter_instance = EntraIDDiagnosticSettingsFilter({}, Mock())
        filter_instance.manager = Mock()
        filter_instance.manager.session_factory = Mock()

        with patch('c7n_azure.graph_utils.local_session', return_value=mock_session):
            with patch('c7n_azure.graph_utils.requests.get', return_value=mock_response):
                # Mock the parent class process method to return the settings (filtered)
                with patch.object(EntraIDDiagnosticSettingsFilter.__bases__[0], 'process',
                                return_value=[{'id': 'setting1', 'name': 'diagnostic1'}]):
                    result = filter_instance.process(resources)

        # If diagnostic settings match filter criteria, should return all resources
        self.assertEqual(result, resources)

    def test_process_no_matching_settings(self):
        """Test when diagnostic settings don't match filter criteria"""
        resources = [{'id': 'resource1'}, {'id': 'resource2'}]

        mock_session = Mock()
        mock_credentials = Mock()
        mock_token = Mock()
        mock_token.token = 'fake-token'
        mock_credentials.get_token.return_value = mock_token
        mock_session.get_credentials.return_value = mock_credentials

        mock_response = Mock()
        mock_response.json.return_value = {
            'value': [
                {'id': 'setting1', 'name': 'diagnostic1'}
            ]
        }

        filter_instance = EntraIDDiagnosticSettingsFilter({}, Mock())
        filter_instance.manager = Mock()
        filter_instance.manager.session_factory = Mock()

        with patch('c7n_azure.graph_utils.local_session', return_value=mock_session):
            with patch('c7n_azure.graph_utils.requests.get', return_value=mock_response):
                # Mock the parent class process method to return empty (no match)
                with patch.object(EntraIDDiagnosticSettingsFilter.__bases__[0], 'process',
                                return_value=[]):
                    result = filter_instance.process(resources)

        # If no diagnostic settings match, should return empty list
        self.assertEqual(result, [])
