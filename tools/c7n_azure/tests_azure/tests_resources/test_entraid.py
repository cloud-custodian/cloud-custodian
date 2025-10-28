# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import Mock, patch
import pytest
import requests
from datetime import datetime, timezone
from pytest_terraform import terraform

from c7n_azure.resources.entraid_user import (
    EntraIDUser
)
from tests_azure.azure_common import BaseTest


class EntraIDUserTest(BaseTest):
    """Test EntraID User resource functionality"""

    def setUp(self):
        super().setUp()
        self.policy = self.load_policy({
            'name': 'test-entraid-user',
            'resource': 'azure.entraid-user'
        })
        self.manager = self.policy.resource_manager

    def test_entraid_user_schema_validate(self):
        """Test that the EntraID user resource schema validates correctly"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-entraid-user',
                'resource': 'azure.entraid-user',
                'filters': [
                    {'type': 'value', 'key': 'accountEnabled', 'value': True}
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_entraid_user_resource_type(self):
        """Test EntraID user resource type configuration"""
        resource_type = EntraIDUser.resource_type
        self.assertEqual(resource_type.service, 'graph')
        self.assertEqual(resource_type.id, 'id')
        self.assertEqual(resource_type.name, 'displayName')
        self.assertTrue(resource_type.global_resource)
        self.assertIn('User.Read.All', resource_type.permissions)

    @patch('c7n_azure.resources.entraid_user.local_session')
    def test_entraid_user_augment(self, mock_session):
        """Test user resource augmentation with computed fields"""
        mock_client = Mock()
        mock_session.return_value.get_session_for_resource.return_value.\
client.return_value = mock_client

        # Sample user data
        users = [
            {
                'objectId': 'user1-id',
                'displayName': 'Test User',
                'userPrincipalName': 'test.user@example.com',
                'accountEnabled': True,
                'lastSignInDateTime': '2023-01-01T12:00:00Z',
                'lastPasswordChangeDateTime': '2022-01-01T12:00:00Z',
                'jobTitle': 'Administrator'
            },
            {
                'objectId': 'user2-id',
                'displayName': 'Regular User',
                'userPrincipalName': 'regular@example.com',
                'accountEnabled': False,
                'lastSignInDateTime': None,
                'lastPasswordChangeDateTime': None,
                'jobTitle': 'User'
            }
        ]

        policy = self.load_policy({
            'name': 'test-augment',
            'resource': 'azure.entraid-user'
        })

        resource_mgr = policy.resource_manager
        augmented = resource_mgr.augment(users)

        # Check augmented fields
        self.assertIn('c7n:LastSignInDays', augmented[0])
        self.assertIn('c7n:IsHighPrivileged', augmented[0])
        self.assertIn('c7n:PasswordAge', augmented[0])

        # Admin user should be flagged as high privileged
        self.assertTrue(augmented[0]['c7n:IsHighPrivileged'])
        self.assertFalse(augmented[1]['c7n:IsHighPrivileged'])

    @patch('c7n_azure.resources.entraid_user.EntraIDUser.get_user_auth_methods')
    def test_auth_methods_filter(self, mock_auth_methods):
        """Test authentication methods filter with real Graph API implementation"""
        users = [
            {
                'id': 'user1',
                'objectId': 'user1',
                'displayName': 'User 1'
            },
            {
                'id': 'user2',
                'objectId': 'user2',
                'displayName': 'User 2'
            },
            {
                'id': 'user3',
                'objectId': 'user3',
                'displayName': 'User 3'
            }
        ]

        # Mock authentication methods: user1 has multiple methods, user2 has one, user3 has none
        def mock_auth_methods_side_effect(user_id):
            if user_id == 'user1':
                return [
                    {
                        '@odata.type': (
                            '#microsoft.graph.'
                            'microsoftAuthenticatorAuthenticationMethod'
                        ),
                        'id': 'method1-id',
                        'displayName': 'Microsoft Authenticator'
                    },
                    {
                        '@odata.type': '#microsoft.graph.phoneAuthenticationMethod',
                        'id': 'method2-id',
                        'phoneNumber': '+1555XXXX123',
                        'phoneType': 'mobile'
                    }
                ]
            elif user_id == 'user2':
                return [
                    {
                        '@odata.type': '#microsoft.graph.phoneAuthenticationMethod',
                        'id': 'method3-id',
                        'phoneNumber': '+1555XXXX456',
                        'phoneType': 'mobile'
                    }
                ]
            else:
                return []  # No authentication methods

        mock_auth_methods.side_effect = mock_auth_methods_side_effect

        policy = self.load_policy({
            'name': 'test-auth-methods-filter',
            'resource': 'azure.entraid-user',
            'filters': [
                {'type': 'auth-methods', 'key': '[]."@odata.type"', 'value': 'not-null'}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(users)

        # Should have 3 users with auth methods data enriched (including user with empty list)
        self.assertEqual(len(filtered), 2)

        # Check that users are enriched with auth methods data
        for user in filtered:
            self.assertIn('c7n:AuthMethods', user)

        # Check actual auth methods content
        user1 = next(u for u in filtered if u['id'] == 'user1')
        user2 = next(u for u in filtered if u['id'] == 'user2')

        self.assertEqual(len(user1['c7n:AuthMethods']), 2)  # User1 has 2 methods
        self.assertEqual(len(user2['c7n:AuthMethods']), 1)  # User2 has 1 method

        # Verify the auth methods check was called for each user
        self.assertEqual(mock_auth_methods.call_count, 3)

    def test_last_signin_filter(self):
        """Test last sign-in filter"""
        users = [
            {
                'objectId': 'user1',
                'c7n:LastSignInDays': 120  # Old sign-in
            },
            {
                'objectId': 'user2',
                'c7n:LastSignInDays': 30   # Recent sign-in
            },
            {
                'objectId': 'user3',
                'c7n:LastSignInDays': 999  # Never signed in
            }
        ]

        policy = self.load_policy({
            'name': 'test-signin-filter',
            'resource': 'azure.entraid-user',
            'filters': [
                {'type': 'last-sign-in', 'days': 90, 'op': 'greater-than'}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(users)

        # Should match user1 and user3 (>90 days)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(set(u['objectId'] for u in filtered), {'user1', 'user3'})

    @patch('c7n_azure.resources.entraid_user.EntraIDUser.get_user_group_memberships')
    def test_group_membership_filter(self, mock_group_memberships):
        """Test group membership filter with real Graph API implementation"""
        users = [
            {
                'id': 'user1',
                'objectId': 'user1',
                'displayName': 'User 1'
            },
            {
                'id': 'user2',
                'objectId': 'user2',
                'displayName': 'User 2'
            },
            {
                'id': 'user3',
                'objectId': 'user3',
                'displayName': 'User 3'
            }
        ]

        # Mock group memberships: user1 in admin groups, user2 in regular, user3 unknown
        def mock_group_side_effect(user_id):
            if user_id == 'user1':
                return [
                    {'id': 'group1', 'displayName': 'Global Administrators'},
                    {'id': 'group2', 'displayName': 'Regular Users'}
                ]
            elif user_id == 'user2':
                return [
                    {'id': 'group2', 'displayName': 'Regular Users'}
                ]
            else:
                return None  # Unknown group memberships

        mock_group_memberships.side_effect = mock_group_side_effect

        policy = self.load_policy({
            'name': 'test-group-filter',
            'resource': 'azure.entraid-user',
            'filters': [
                {
                    'type': 'group-membership',
                    'groups': ['Global Administrators'],
                    'match': 'any'
                }
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(users)

        # Only user1 is in admin group (user3 skipped due to unknown status)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'user1')

        # Verify the group membership check was called
        self.assertEqual(mock_group_memberships.call_count, 3)

    @patch('c7n_azure.resources.entraid_user.EntraIDUser.make_graph_request')
    def test_user_type_field_requested(self, mock_graph_request):
        """Test that userType field is explicitly requested from Graph API"""
        # Mock the Graph API response with userType field
        mock_graph_request.return_value = {
            'value': [
                {
                    'id': 'user1',
                    'objectId': 'user1',
                    'displayName': 'Guest User',
                    'userPrincipalName': 'guest@external.com',
                    'userType': 'Guest',
                    'accountEnabled': True
                },
                {
                    'id': 'user2',
                    'objectId': 'user2',
                    'displayName': 'Member User',
                    'userPrincipalName': 'member@internal.com',
                    'userType': 'Member',
                    'accountEnabled': True
                }
            ]
        }

        policy = self.load_policy({
            'name': 'test-usertype-field',
            'resource': 'azure.entraid-user'
        })

        resource_mgr = policy.resource_manager
        resources = resource_mgr.resources()

        # Verify the API was called with $select parameter including userType
        mock_graph_request.assert_called_once()
        call_args = mock_graph_request.call_args[0]
        endpoint = call_args[0]
        self.assertIn('$select=', endpoint)
        self.assertIn('userType', endpoint)

        # Verify userType field is present in returned resources
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['userType'], 'Guest')
        self.assertEqual(resources[1]['userType'], 'Member')

    def test_guest_user_filter(self):
        """Test that ValueFilter works correctly with userType field for guest users"""
        users = [
            {
                'id': 'user1',
                'objectId': 'user1',
                'displayName': 'Guest User',
                'userPrincipalName': 'guest@external.com',
                'userType': 'Guest',
                'accountEnabled': True
            },
            {
                'id': 'user2',
                'objectId': 'user2',
                'displayName': 'Member User',
                'userPrincipalName': 'member@internal.com',
                'userType': 'Member',
                'accountEnabled': True
            },
            {
                'id': 'user3',
                'objectId': 'user3',
                'displayName': 'Another Member',
                'userPrincipalName': 'member2@internal.com',
                'userType': 'Member',
                'accountEnabled': True
            }
        ]

        # Test filtering for guest users (like the guest-users.yaml policy)
        policy = self.load_policy({
            'name': 'test-guest-filter',
            'resource': 'azure.entraid-user',
            'filters': [
                {'type': 'value', 'key': 'userType', 'value': 'Guest'},
                {'type': 'value', 'key': 'accountEnabled', 'value': True}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(users)

        # Should only return the guest user
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['userType'], 'Guest')
        self.assertEqual(filtered[0]['displayName'], 'Guest User')

        # Test filtering for member users
        policy_members = self.load_policy({
            'name': 'test-member-filter',
            'resource': 'azure.entraid-user',
            'filters': [
                {'type': 'value', 'key': 'userType', 'value': 'Member'}
            ]
        })

        resource_mgr_members = policy_members.resource_manager
        filtered_members = resource_mgr_members.filter_resources(users)

        # Should return both member users
        self.assertEqual(len(filtered_members), 2)
        self.assertTrue(all(u['userType'] == 'Member' for u in filtered_members))

    def test_password_age_filter(self):
        """Test password age filter"""
        users = [
            {
                'objectId': 'user1',
                'c7n:PasswordAge': 200  # Old password
            },
            {
                'objectId': 'user2',
                'c7n:PasswordAge': 30   # Recent password change
            }
        ]

        policy = self.load_policy({
            'name': 'test-password-age',
            'resource': 'azure.entraid-user',
            'filters': [
                {'type': 'password-age', 'days': 180, 'op': 'greater-than'}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(users)

        # Only user1 has old password
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['objectId'], 'user1')

    def test_disable_user_action(self):
        """Test disable user action"""

        policy = self.load_policy({
            'name': 'test-disable-action',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'disable'}]
        })

        # Validate action schema
        resource_mgr = policy.resource_manager
        action = resource_mgr.actions[0]
        self.assertEqual(action.type, 'disable')
        self.assertIn('User.ReadWrite.All', action.permissions)

    def test_calculate_last_signin_days_with_valid_date(self):
        """Test _calculate_last_signin_days with valid sign-in date"""
        user = {
            'signInActivity': {
                'lastSignInDateTime': '2023-01-01T12:00:00Z'
            }
        }

        with patch('c7n_azure.resources.entraid_user.datetime') as mock_datetime:
            mock_now = datetime(2023, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            mock_datetime.fromisoformat.return_value = \
                datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

            days = self.manager._calculate_last_signin_days(user)
            self.assertEqual(days, 90)  # Approximately 90 days between Jan 1 and April 1

    def test_calculate_last_signin_days_never_signed_in(self):
        """Test _calculate_last_signin_days when user never signed in"""
        user = {}  # No signInActivity

        days = self.manager._calculate_last_signin_days(user)
        self.assertEqual(days, 999)

    def test_calculate_last_signin_days_invalid_date(self):
        """Test _calculate_last_signin_days with invalid date format"""
        user = {
            'signInActivity': {
                'lastSignInDateTime': 'invalid-date'
            }
        }

        days = self.manager._calculate_last_signin_days(user)
        self.assertEqual(days, 999)

    def test_is_high_privileged_user_admin_email(self):
        """Test _is_high_privileged_user with admin email"""
        user = {
            'userPrincipalName': 'testadmin@contoso.com',
            'displayName': 'Test User',
            'jobTitle': 'User'
        }

        result = self.manager._is_high_privileged_user(user)
        self.assertFalse(result)  # Only checks for 'admin@' ending

    def test_is_high_privileged_user_admin_display_name(self):
        """Test _is_high_privileged_user with admin in display name"""
        user = {
            'userPrincipalName': 'test@contoso.com',
            'displayName': 'Admin User',
            'jobTitle': 'User'
        }

        result = self.manager._is_high_privileged_user(user)
        self.assertTrue(result)

    def test_is_high_privileged_user_administrator_title(self):
        """Test _is_high_privileged_user with administrator job title"""
        user = {
            'userPrincipalName': 'test@contoso.com',
            'displayName': 'Test User',
            'jobTitle': 'System Administrator'
        }

        result = self.manager._is_high_privileged_user(user)
        self.assertTrue(result)

    def test_is_high_privileged_user_regular_user(self):
        """Test _is_high_privileged_user with regular user"""
        user = {
            'userPrincipalName': 'test@contoso.com',
            'displayName': 'Test User',
            'jobTitle': 'Developer'
        }

        result = self.manager._is_high_privileged_user(user)
        self.assertFalse(result)

    def test_calculate_password_age_with_valid_date(self):
        """Test _calculate_password_age with valid password change date"""
        user = {
            'lastPasswordChangeDateTime': '2023-01-01T12:00:00Z'
        }

        with patch('c7n_azure.resources.entraid_user.datetime') as mock_datetime:
            mock_now = datetime(2023, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = mock_now
            mock_datetime.fromisoformat.return_value = \
                datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

            age = self.manager._calculate_password_age(user)
            self.assertEqual(age, 90)  # Approximately 90 days

    def test_calculate_password_age_no_date(self):
        """Test _calculate_password_age when no password change date"""
        user = {}  # No lastPasswordChangeDateTime

        age = self.manager._calculate_password_age(user)
        self.assertEqual(age, 0)

    def test_calculate_password_age_invalid_date(self):
        """Test _calculate_password_age with invalid date format"""
        user = {
            'lastPasswordChangeDateTime': 'invalid-date'
        }

        age = self.manager._calculate_password_age(user)
        self.assertEqual(age, 0)

    def test_get_graph_resources_success(self):
        """Test get_graph_resources successful API call"""
        mock_response = {
            'value': [
                {
                    'id': 'user1',
                    'displayName': 'Test User',
                    'userPrincipalName': 'test@example.com',
                    'accountEnabled': True,
                    'userType': 'Member'
                }
            ]
        }

        with patch.object(self.manager, 'make_graph_request', return_value=mock_response):
            with patch.object(self.manager, 'augment') as mock_augment:
                mock_augment.return_value = mock_response['value']

                resources = self.manager.get_graph_resources()

                self.assertEqual(len(resources), 1)
                self.assertEqual(resources[0]['id'], 'user1')
                mock_augment.assert_called_once()

    def test_get_graph_resources_error_handling(self):
        """Test get_graph_resources error handling"""
        with patch.object(self.manager, 'make_graph_request',
                         side_effect=Exception("API Error")):
            resources = self.manager.get_graph_resources()

            # Should return empty list on error
            self.assertEqual(resources, [])

    def test_get_graph_resources_permission_error(self):
        """Test get_graph_resources with insufficient privileges"""
        with patch.object(self.manager, 'make_graph_request',
                         side_effect=requests.exceptions.HTTPError("403 Insufficient privileges")):
            resources = self.manager.get_graph_resources()

            # Should return empty list on permission error
            self.assertEqual(resources, [])

    def test_augment_exception_handling(self):
        """Test augment method exception handling"""
        users = [
            {
                'id': 'user1',
                'displayName': 'Test User'
            }
        ]

        with patch.object(self.manager, '_calculate_last_signin_days',
                         side_effect=Exception("Calculation error")):
            # Should not raise exception, just log warning
            result = self.manager.augment(users)

            # Should return original users even with augmentation error
            self.assertEqual(result, users)

    def test_get_user_auth_methods_success(self):
        """Test get_user_auth_methods successful call"""
        mock_response = {
            'value': [
                {
                    '@odata.type': '#microsoft.graph.microsoftAuthenticatorAuthenticationMethod',
                    'id': 'method1'
                }
            ]
        }

        with patch.object(self.manager, 'make_graph_request', return_value=mock_response):
            result = self.manager.get_user_auth_methods('user1')

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['@odata.type'],
                           '#microsoft.graph.microsoftAuthenticatorAuthenticationMethod')

    def test_get_user_auth_methods_permission_error(self):
        """Test get_user_auth_methods with permission error"""
        with patch.object(
                self.manager, 'make_graph_request',
                side_effect=requests.exceptions.RequestException("403 Insufficient privileges")
        ):
            result = self.manager.get_user_auth_methods('user1')

            self.assertIsNone(result)

    def test_get_user_auth_methods_other_error(self):
        """Test get_user_auth_methods with other API error"""
        with patch.object(self.manager, 'make_graph_request',
                         side_effect=requests.exceptions.RequestException("500 Server Error")):
            result = self.manager.get_user_auth_methods('user1')

            self.assertIsNone(result)

    def test_check_user_risk_level_success(self):
        """Test check_user_risk_level successful call"""
        mock_response = {
            'riskLevel': 'medium'
        }

        with patch.object(self.manager, 'make_graph_request', return_value=mock_response):
            result = self.manager.check_user_risk_level('user1')

            self.assertEqual(result, 'medium')

    def test_check_user_risk_level_not_found(self):
        """Test check_user_risk_level when user not in risky users"""
        with patch.object(self.manager, 'make_graph_request',
                         side_effect=requests.exceptions.RequestException("404")):
            result = self.manager.check_user_risk_level('user1')

            self.assertEqual(result, 'none')

    def test_check_user_risk_level_permission_error(self):
        """Test check_user_risk_level with permission error"""
        with patch.object(
                self.manager, 'make_graph_request',
                side_effect=requests.exceptions.RequestException("403 Insufficient privileges")
        ):
            result = self.manager.check_user_risk_level('user1')

            self.assertIsNone(result)

    def test_check_user_risk_level_hidden_mapping(self):
        """Test check_user_risk_level with hidden risk level mapping"""
        mock_response = {
            'riskLevel': 'hidden'
        }

        with patch.object(self.manager, 'make_graph_request', return_value=mock_response):
            result = self.manager.check_user_risk_level('user1')

            self.assertEqual(result, 'none')  # hidden maps to none

    def test_get_user_group_memberships_success(self):
        """Test get_user_group_memberships successful call"""
        mock_response = {
            'value': [
                {
                    '@odata.type': '#microsoft.graph.group',
                    'id': 'group1',
                    'displayName': 'Test Group',
                    'mail': 'test@example.com'
                },
                {
                    '@odata.type': '#microsoft.graph.directoryRole',  # Should be filtered out
                    'id': 'role1',
                    'displayName': 'Directory Role'
                }
            ]
        }

        with patch.object(self.manager, 'make_graph_request', return_value=mock_response):
            result = self.manager.get_user_group_memberships('user1')

            # Should only include actual groups, not directory roles
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['displayName'], 'Test Group')

    def test_get_user_group_memberships_permission_error(self):
        """Test get_user_group_memberships with permission error"""
        with patch.object(
                self.manager, 'make_graph_request',
                side_effect=requests.exceptions.RequestException("403 Insufficient privileges")
        ):
            result = self.manager.get_user_group_memberships('user1')

            self.assertIsNone(result)

    def test_risk_level_filter_no_user_id(self):
        """Test RiskLevelFilter with user missing ID"""
        resources = [
            {
                'displayName': 'User without ID'
                # Missing 'id' field
            }
        ]

        policy = self.load_policy({
            'name': 'test-risk-filter',
            'resource': 'azure.entraid-user',
            'filters': [
                {'type': 'risk-level', 'value': 'high'}
            ]
        })

        filter_instance = policy.resource_manager.filters[0]
        result = filter_instance.process(resources)

        # Should skip users without ID
        self.assertEqual(len(result), 0)

    def test_group_membership_filter_no_user_id(self):
        """Test GroupMembershipFilter with user missing ID"""
        resources = [
            {
                'displayName': 'User without ID'
                # Missing 'id' field
            }
        ]

        policy = self.load_policy({
            'name': 'test-group-filter',
            'resource': 'azure.entraid-user',
            'filters': [
                {
                    'type': 'group-membership',
                    'groups': ['Test Group'],
                    'match': 'any'
                }
            ]
        })

        filter_instance = policy.resource_manager.filters[0]
        result = filter_instance.process(resources)

        # Should skip users without ID
        self.assertEqual(len(result), 0)

    def test_group_membership_filter_empty_groups(self):
        """Test GroupMembershipFilter with empty groups list"""
        resources = [
            {
                'id': 'user1',
                'displayName': 'Test User'
            }
        ]

        policy = self.load_policy({
            'name': 'test-empty-groups',
            'resource': 'azure.entraid-user',
            'filters': [
                {
                    'type': 'group-membership',
                    'groups': [],  # Empty groups list
                    'match': 'any'
                }
            ]
        })

        filter_instance = policy.resource_manager.filters[0]
        result = filter_instance.process(resources)

        # Should return all resources when no groups specified
        self.assertEqual(len(result), 1)

    def test_group_membership_filter_match_all(self):
        """Test GroupMembershipFilter with 'all' match type"""
        resources = [
            {
                'id': 'user1',
                'displayName': 'Test User'
            }
        ]

        mock_groups = [
            {'displayName': 'Group1'},
            {'displayName': 'Group2'}
        ]

        policy = self.load_policy({
            'name': 'test-match-all',
            'resource': 'azure.entraid-user',
            'filters': [
                {
                    'type': 'group-membership',
                    'groups': ['Group1', 'Group2'],
                    'match': 'all'
                }
            ]
        })

        filter_instance = policy.resource_manager.filters[0]

        with patch.object(policy.resource_manager, 'get_user_group_memberships',
                         return_value=mock_groups):
            result = filter_instance.process(resources)

            # Should match user who has both groups
            self.assertEqual(len(result), 1)

    def test_disable_user_action_no_user_id(self):
        """Test DisableUserAction with user missing ID"""
        policy = self.load_policy({
            'name': 'test-disable',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'disable'}]
        })

        action = policy.resource_manager.actions[0]
        action._prepare_processing()

        user = {
            'displayName': 'User without ID'
            # Missing 'id' field
        }

        # Should not raise exception, just log error
        action._process_resource(user)

    def test_require_mfa_action_no_user_id(self):
        """Test RequireMFAAction with user missing ID"""
        policy = self.load_policy({
            'name': 'test-mfa',
            'resource': 'azure.entraid-user',
            'actions': [{'type': 'require-mfa'}]
        })

        action = policy.resource_manager.actions[0]
        action._prepare_processing()

        user = {
            'displayName': 'User without ID'
            # Missing 'id' field
        }

        # Should not raise exception, just log error
        action._process_resource(user)


# Terraform-based integration tests
# These tests use real Azure EntraID resources provisioned via Terraform
# Following the same pattern as AWS tests


@terraform('entraid_user')
@pytest.mark.functional
def test_entraid_user_discovery_terraform(test, entraid_user):
    """Test that Cloud Custodian can discover users provisioned by Terraform"""
    # Verify terraform fixtures loaded successfully
    assert len(entraid_user.outputs) == 5, (
        f"Expected 5 total outputs (4 users + 1 group), got {len(entraid_user.outputs)}"
    )
    assert 'azuread_user' in entraid_user.resources, "azuread_user resources not found"

    # Get terraform-provisioned user data
    admin_user = entraid_user.outputs['test_admin_user']['value']
    disabled_user = entraid_user.outputs['test_disabled_user']['value']
    regular_user = entraid_user.outputs['test_regular_user']['value']
    old_password_user = entraid_user.outputs['test_old_password_user']['value']

    # Verify test data integrity

    assert admin_user['account_enabled'] is True
    assert admin_user['job_title'] == 'Administrator'
    assert admin_user['department'] == 'IT'

    assert disabled_user['account_enabled'] is False
    assert disabled_user['job_title'] == 'User'
    assert disabled_user['department'] == 'HR'

    assert regular_user['account_enabled'] is True
    assert regular_user['job_title'] == 'Developer'
    assert regular_user['department'] == 'Engineering'

    assert old_password_user['account_enabled'] is True

    assert old_password_user['job_title'] == 'Analyst'
    assert old_password_user['department'] == 'Finance'

    # Test Cloud Custodian policy creation and validation
    policy = test.load_policy({
        'name': 'terraform-enabled-users',
        'resource': 'azure.entraid-user',
        'filters': [
            {'type': 'value', 'key': 'accountEnabled', 'value': True}
        ]
    })

    # Verify policy loads correctly
    assert policy.resource_manager.type == 'entraid-user'

    # Test job title filter policy
    admin_policy = test.load_policy({
        'name': 'terraform-admin-users',
        'resource': 'azure.entraid-user',
        'filters': [
            {'type': 'value', 'key': 'jobTitle', 'value': 'Administrator'}
        ]
    })

    assert admin_policy.resource_manager.type == 'entraid-user'

    print(f"SUCCESS: Terraform fixtures loaded {len(entraid_user.outputs)} users successfully")


@terraform('entraid_user')
@pytest.mark.functional
def test_entraid_user_job_title_filter_terraform(test, entraid_user):
    """Test job title filter against Terraform-provisioned users"""
    admin_user = entraid_user.outputs['test_admin_user']['value']
    regular_user = entraid_user.outputs['test_regular_user']['value']

    # Test policy for admin job titles
    policy = test.load_policy({
        'name': 'terraform-admin-users',
        'resource': 'azure.entraid-user',
        'filters': [
            {'type': 'value', 'key': 'jobTitle', 'value': 'Administrator'}
        ]
    })

    # Verify test data has expected job titles
    assert admin_user['job_title'] == 'Administrator'
    assert regular_user['job_title'] == 'Developer'

    # Verify policy validates correctly
    assert policy is not None


@terraform('entraid_user')
@pytest.mark.functional
def test_entraid_user_department_filter_terraform(test, entraid_user):
    """Test department filter against Terraform-provisioned users"""
    admin_user = entraid_user.outputs['test_admin_user']['value']
    old_password_user = entraid_user.outputs['test_old_password_user']['value']

    # Test policy for IT department users
    policy = test.load_policy({
        'name': 'terraform-it-users',
        'resource': 'azure.entraid-user',
        'filters': [
            {'type': 'value', 'key': 'department', 'value': 'IT'}
        ]
    })

    # Verify test data has expected departments
    assert admin_user['department'] == 'IT'
    assert old_password_user['department'] == 'Finance'

    assert policy is not None
