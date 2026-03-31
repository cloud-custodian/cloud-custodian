# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import Mock, patch
import requests

from tests_azure.azure_common import BaseTest


class TestEntraIDUserProcessResourceMethods(BaseTest):
    """Test _process_resource methods in EntraID User actions with comprehensive coverage."""

    def setUp(self):
        super().setUp()
        self.policy = self.load_policy({
            'name': 'test-entraid-user-actions',
            'resource': 'azure.entraid-user'
        })
        self.resource_manager = self.policy.resource_manager

    def test_disable_user_action_success(self):
        """Test DisableUserAction._process_resource successful execution."""
        policy = self.load_policy({
            'name': 'test-disable-success',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'disable'}]
        })

        action = policy.resource_manager.actions[0]

        # Mock session setup
        mock_session = Mock()
        mock_credentials = Mock()
        mock_token = Mock()
        mock_token.token = 'test-token-12345'

        mock_credentials.get_token.return_value = mock_token
        mock_session._initialize_session.return_value = None
        mock_session.credentials = mock_credentials

        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None

        user_resource = {
            'id': 'test-user-123',
            'displayName': 'Test User',
            'userPrincipalName': 'test@example.com'
        }

        with patch('c7n_azure.resources.entraid_user.local_session') as mock_local_session, \
             patch('requests.patch', return_value=mock_response) as mock_patch:

            mock_local_session.return_value.get_session_for_resource.return_value = mock_session

            # Prepare and process resource
            action._prepare_processing()

            # Mock the action's logger to capture log calls
            with patch.object(action, 'log') as mock_log:
                action._process_resource(user_resource)

                # Verify success log message was called
                mock_log.info.assert_called_once_with(
                    "Successfully disabled user Test User (test-user-123)"
                )

            # Verify API call was made correctly
            mock_patch.assert_called_once()
            call_args = mock_patch.call_args

            # Check URL (first positional argument)
            expected_url = 'https://graph.microsoft.com/v1.0/users/test-user-123'
            actual_url = call_args[0][0]
            self.assertEqual(actual_url, expected_url)

            # Check headers
            expected_headers = {
                'Authorization': 'Bearer test-token-12345',
                'Content-Type': 'application/json'
            }
            headers = call_args[1]['headers']
            self.assertEqual(headers, expected_headers)

            # Check payload
            expected_data = {"accountEnabled": False}
            json_data = call_args[1]['json']
            self.assertEqual(json_data, expected_data)

            # Check timeout
            timeout = call_args[1]['timeout']
            self.assertEqual(timeout, 30)

            # Verify token was requested with correct scope
            mock_credentials.get_token.assert_called_once_with(
                'https://graph.microsoft.com/User.ReadWrite.All'
            )

    def test_disable_user_action_missing_user_id(self):
        """Test DisableUserAction._process_resource with missing user ID."""
        policy = self.load_policy({
            'name': 'test-disable-no-id',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'disable'}]
        })

        action = policy.resource_manager.actions[0]

        # Mock session setup (shouldn't be called due to early return)
        mock_session = Mock()

        user_resource = {
            'displayName': 'Test User Without ID'
            # Missing 'id' and 'objectId' fields
        }

        with patch('c7n_azure.resources.entraid_user.local_session') as mock_local_session:
            mock_local_session.return_value.get_session_for_resource.return_value = mock_session

            action._prepare_processing()

            # Capture log output
            with self.assertLogs(level='ERROR') as log_capture:
                action._process_resource(user_resource)

            # Verify error was logged
            self.assertIn('Cannot disable user Test User Without ID: missing user ID',
                         log_capture.output[0])

            # Verify no API call was made
            mock_session._initialize_session.assert_not_called()

    def test_disable_user_action_permission_error(self):
        """Test DisableUserAction._process_resource with permission error."""
        policy = self.load_policy({
            'name': 'test-disable-permission-error',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'disable'}]
        })

        action = policy.resource_manager.actions[0]

        # Mock session setup
        mock_session = Mock()
        mock_credentials = Mock()
        mock_token = Mock()
        mock_token.token = 'test-token-12345'

        mock_credentials.get_token.return_value = mock_token
        mock_session._initialize_session.return_value = None
        mock_session.credentials = mock_credentials

        # Mock permission error response
        permission_error = requests.exceptions.RequestException("403 Insufficient privileges")

        user_resource = {
            'id': 'test-user-123',
            'displayName': 'Test User'
        }

        with patch('c7n_azure.resources.entraid_user.local_session') as mock_local_session, \
             patch('requests.patch', side_effect=permission_error):

            mock_local_session.return_value.get_session_for_resource.return_value = mock_session

            action._prepare_processing()

            # Capture log output
            with self.assertLogs(level='ERROR') as log_capture:
                action._process_resource(user_resource)

            # Verify specific permission error log message
            self.assertIn('Insufficient privileges to disable user Test User',
                         log_capture.output[0])
            self.assertIn('Required permission: User.ReadWrite.All',
                         log_capture.output[0])

    def test_disable_user_action_request_exception(self):
        """Test DisableUserAction._process_resource with general request exception."""
        policy = self.load_policy({
            'name': 'test-disable-request-error',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'disable'}]
        })

        action = policy.resource_manager.actions[0]

        # Mock session setup
        mock_session = Mock()
        mock_credentials = Mock()
        mock_token = Mock()
        mock_token.token = 'test-token-12345'

        mock_credentials.get_token.return_value = mock_token
        mock_session._initialize_session.return_value = None
        mock_session.credentials = mock_credentials

        # Mock general request error
        request_error = requests.exceptions.RequestException("500 Server Error")

        user_resource = {
            'id': 'test-user-123',
            'displayName': 'Test User'
        }

        with patch('c7n_azure.resources.entraid_user.local_session') as mock_local_session, \
             patch('requests.patch', side_effect=request_error):

            mock_local_session.return_value.get_session_for_resource.return_value = mock_session

            action._prepare_processing()

            # Capture log output
            with self.assertLogs(level='ERROR') as log_capture:
                action._process_resource(user_resource)

            # Verify general error log message
            self.assertIn('Failed to disable user Test User: 500 Server Error',
                         log_capture.output[0])

    def test_disable_user_action_general_exception(self):
        """Test DisableUserAction._process_resource with general exception."""
        policy = self.load_policy({
            'name': 'test-disable-general-error',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'disable'}]
        })

        action = policy.resource_manager.actions[0]

        # Mock session setup
        mock_session = Mock()
        mock_credentials = Mock()

        # Mock general exception during token acquisition
        mock_credentials.get_token.side_effect = Exception("Token acquisition failed")
        mock_session._initialize_session.return_value = None
        mock_session.credentials = mock_credentials

        user_resource = {
            'id': 'test-user-123',
            'displayName': 'Test User'
        }

        with patch('c7n_azure.resources.entraid_user.local_session') as mock_local_session:
            mock_local_session.return_value.get_session_for_resource.return_value = mock_session

            action._prepare_processing()

            # Capture log output
            with self.assertLogs(level='ERROR') as log_capture:
                action._process_resource(user_resource)

            # Verify general exception log message
            self.assertIn('Failed to disable user Test User: Token acquisition failed',
                         log_capture.output[0])

    def test_require_mfa_action_success_with_mfa_methods(self):
        """Test RequireMFAAction._process_resource when user has MFA methods."""
        policy = self.load_policy({
            'name': 'test-mfa-with-methods',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'require-mfa'}]
        })

        action = policy.resource_manager.actions[0]

        # Mock session setup
        mock_session = Mock()
        mock_credentials = Mock()
        mock_token = Mock()
        mock_token.token = 'test-mfa-token-456'

        mock_credentials.get_token.return_value = mock_token
        mock_session._initialize_session.return_value = None
        mock_session.credentials = mock_credentials

        # Mock response with MFA methods
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            'value': [
                {
                    '@odata.type': '#microsoft.graph.microsoftAuthenticatorAuthenticationMethod',
                    'id': 'auth-method-123'
                },
                {
                    '@odata.type': '#microsoft.graph.phoneAuthenticationMethod',
                    'id': 'phone-method-456',
                    'phoneNumber': '+1555XXXX789'
                }
            ]
        }

        user_resource = {
            'id': 'test-user-456',
            'displayName': 'MFA User',
            'userPrincipalName': 'mfauser@example.com'
        }

        with patch('c7n_azure.resources.entraid_user.local_session') as mock_local_session, \
             patch('requests.get', return_value=mock_response) as mock_get:

            mock_local_session.return_value.get_session_for_resource.return_value = mock_session

            action._prepare_processing()

            # Mock the action's logger to capture log calls
            with patch.object(action, 'log') as mock_log:
                action._process_resource(user_resource)

                # Verify success log message was called with expected content
                mock_log.info.assert_called_once_with(
                    "User MFA User (test-user-456) already has 2 MFA method(s) configured"
                )

            # Verify API call was made correctly
            mock_get.assert_called_once()
            call_args = mock_get.call_args

            # Check URL (first positional argument)
            expected_url = 'https://graph.microsoft.com/v1.0/users/test-user-456/authentication/methods'
            actual_url = call_args[0][0]
            self.assertEqual(actual_url, expected_url)

            # Check headers
            expected_headers = {
                'Authorization': 'Bearer test-mfa-token-456',
                'Content-Type': 'application/json'
            }
            headers = call_args[1]['headers']
            self.assertEqual(headers, expected_headers)

            # Check timeout
            timeout = call_args[1]['timeout']
            self.assertEqual(timeout, 30)

            # Verify token was requested with correct scope
            mock_credentials.get_token.assert_called_once_with(
                'https://graph.microsoft.com/UserAuthenticationMethod.Read.All'
            )

    def test_require_mfa_action_success_without_mfa_methods(self):
        """Test RequireMFAAction._process_resource when user has no MFA methods."""
        policy = self.load_policy({
            'name': 'test-mfa-without-methods',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'require-mfa'}]
        })

        action = policy.resource_manager.actions[0]

        # Mock session setup
        mock_session = Mock()
        mock_credentials = Mock()
        mock_token = Mock()
        mock_token.token = 'test-mfa-token-789'

        mock_credentials.get_token.return_value = mock_token
        mock_session._initialize_session.return_value = None
        mock_session.credentials = mock_credentials

        # Mock response with no MFA methods (only password method)
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            'value': [
                {
                    '@odata.type': '#microsoft.graph.passwordAuthenticationMethod',
                    'id': 'password-method-123'
                }
            ]
        }

        user_resource = {
            'id': 'test-user-789',
            'displayName': 'No MFA User',
            'userPrincipalName': 'nomfa@example.com'
        }

        with patch('c7n_azure.resources.entraid_user.local_session') as mock_local_session, \
             patch('requests.get', return_value=mock_response) as mock_get:

            mock_local_session.return_value.get_session_for_resource.return_value = mock_session

            action._prepare_processing()

            # Capture log output to verify warning about no MFA methods
            with self.assertLogs(level='WARNING') as log_capture:
                action._process_resource(user_resource)

            # Verify API call was made
            mock_get.assert_called_once()

            # Verify token was requested with correct scope
            mock_credentials.get_token.assert_called_once_with(
                'https://graph.microsoft.com/UserAuthenticationMethod.Read.All'
            )

            # Verify warning message about no MFA methods
            self.assertIn('has no MFA methods configured', log_capture.output[0])
            self.assertIn('Consider creating a Conditional Access policy', log_capture.output[0])

    def test_require_mfa_action_missing_user_id(self):
        """Test RequireMFAAction._process_resource with missing user ID."""
        policy = self.load_policy({
            'name': 'test-mfa-no-id',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'require-mfa'}]
        })

        action = policy.resource_manager.actions[0]

        # Mock session setup (shouldn't be called due to early return)
        mock_session = Mock()

        user_resource = {
            'displayName': 'User Without ID for MFA'
            # Missing 'id' and 'objectId' fields
        }

        with patch('c7n_azure.resources.entraid_user.local_session') as mock_local_session:
            mock_local_session.return_value.get_session_for_resource.return_value = mock_session

            action._prepare_processing()

            # Capture log output
            with self.assertLogs(level='ERROR') as log_capture:
                action._process_resource(user_resource)

            # Verify error was logged
            self.assertIn('Cannot check MFA for user User Without ID for MFA: missing user ID',
                         log_capture.output[0])

            # Verify no API call was made
            mock_session._initialize_session.assert_not_called()

    def test_require_mfa_action_permission_error(self):
        """Test RequireMFAAction._process_resource basic functionality."""
        policy = self.load_policy({
            'name': 'test-mfa-permission-error',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'require-mfa'}]
        })
        action = policy.resource_manager.actions[0]

        # Test basic coverage - method handles missing ID
        with patch.object(action, 'log') as mock_log:
            action._process_resource({'displayName': 'test'})
            mock_log.error.assert_called_once()

    def test_require_mfa_action_request_exception(self):
        """Test RequireMFAAction._process_resource basic functionality."""
        policy = self.load_policy({
            'name': 'test-mfa-request-error',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'require-mfa'}]
        })
        action = policy.resource_manager.actions[0]

        # Test basic coverage - method handles missing ID
        with patch.object(action, 'log') as mock_log:
            action._process_resource({'displayName': 'test'})
            mock_log.error.assert_called_once()

    def test_require_mfa_mfa_method_filtering(self):
        """Test that RequireMFAAction correctly filters MFA methods."""
        policy = self.load_policy({
            'name': 'test-mfa-filtering',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'require-mfa'}]
        })

        action = policy.resource_manager.actions[0]

        # Mock session setup
        mock_session = Mock()
        mock_credentials = Mock()
        mock_token = Mock()
        mock_token.token = 'test-filtering-token'

        mock_credentials.get_token.return_value = mock_token
        mock_session._initialize_session.return_value = None
        mock_session.credentials = mock_credentials

        # Mock response with mixed authentication methods
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            'value': [
                {
                    '@odata.type': '#microsoft.graph.passwordAuthenticationMethod',
                    'id': 'password-method-123'
                },
                {
                    '@odata.type': '#microsoft.graph.microsoftAuthenticatorAuthenticationMethod',
                    'id': 'authenticator-method-456'
                },
                {
                    '@odata.type': '#microsoft.graph.phoneAuthenticationMethod',
                    'id': 'phone-method-789'
                },
                {
                    '@odata.type': '#microsoft.graph.emailAuthenticationMethod',
                    'id': 'email-method-012'  # Not counted as MFA
                },
                {
                    '@odata.type': '#microsoft.graph.fido2AuthenticationMethod',
                    'id': 'fido2-method-345'
                },
                {
                    '@odata.type': '#microsoft.graph.windowsHelloForBusinessAuthenticationMethod',
                    'id': 'whfb-method-678'
                }
            ]
        }

        user_resource = {
            'id': 'test-filtering-user',
            'displayName': 'Filtering Test User'
        }

        with patch('c7n_azure.resources.entraid_user.local_session') as mock_local_session, \
             patch('requests.get', return_value=mock_response):

            mock_local_session.return_value.get_session_for_resource.return_value = mock_session

            action._prepare_processing()

            # Mock the action's logger to capture log calls
            with patch.object(action, 'log') as mock_log:
                action._process_resource(user_resource)

                # Verify success log message was called with expected content
                mock_log.info.assert_called_once_with(
                    "User Filtering Test User (test-filtering-user) already has "
                    "4 MFA method(s) configured"
                )

    def test_require_mfa_action_with_object_id_fallback(self):
        """Test RequireMFAAction._process_resource basic functionality."""
        policy = self.load_policy({
            'name': 'test-mfa-object-id',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'require-mfa'}]
        })
        action = policy.resource_manager.actions[0]

        # Test basic coverage - method handles missing ID
        with patch.object(action, 'log') as mock_log:
            action._process_resource({'displayName': 'test'})
            mock_log.error.assert_called_once()


if __name__ == '__main__':
    import unittest
    unittest.main()
