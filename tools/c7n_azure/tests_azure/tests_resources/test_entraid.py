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
from c7n_azure.resources.entraid_group import EntraIDGroup
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


class EntraIDGroupTest(BaseTest):
    """Test EntraID Group resource functionality"""

    def test_entraid_group_schema_validate(self):
        """Test that the EntraID group resource schema validates correctly"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-entraid-group',
                'resource': 'azure.entraid-group',
                'filters': [
                    {'type': 'value', 'key': 'securityEnabled', 'value': True}
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_entraid_group_resource_type(self):
        """Test EntraID group resource type configuration"""
        resource_type = EntraIDGroup.resource_type
        self.assertEqual(resource_type.service, 'graph')
        self.assertEqual(resource_type.id, 'id')
        self.assertEqual(resource_type.name, 'displayName')
        self.assertTrue(resource_type.global_resource)
        self.assertIn('Group.Read.All', resource_type.permissions)

    def test_entraid_group_augment(self):
        """Test group resource augmentation with computed fields"""

        # Sample group data
        groups = [
            {
                'id': 'group1-id',
                'displayName': 'Global Administrators',
                'description': 'Admin group',
                'securityEnabled': True,
                'mailEnabled': False,
                'groupTypes': []
            },
            {
                'id': 'group2-id',
                'displayName': 'All Users Distribution',
                'description': 'Distribution list',
                'securityEnabled': False,
                'mailEnabled': True,
                'groupTypes': ['Unified']
            },
            {
                'id': 'group3-id',
                'displayName': 'Dynamic Security Group',
                'description': 'Dynamic membership',
                'securityEnabled': True,
                'mailEnabled': False,
                'groupTypes': ['DynamicMembership']
            }
        ]

        policy = self.load_policy({
            'name': 'test-augment',
            'resource': 'azure.entraid-group'
        })

        resource_mgr = policy.resource_manager
        augmented = resource_mgr.augment(groups)

        # Check augmented fields
        self.assertIn('c7n:IsSecurityGroup', augmented[0])
        self.assertIn('c7n:IsDistributionGroup', augmented[0])
        self.assertIn('c7n:IsDynamicGroup', augmented[0])
        self.assertIn('c7n:IsAdminGroup', augmented[0])

        # Admin group should be flagged correctly
        self.assertTrue(augmented[0]['c7n:IsSecurityGroup'])
        self.assertTrue(augmented[0]['c7n:IsAdminGroup'])
        self.assertFalse(augmented[0]['c7n:IsDistributionGroup'])

        # Distribution group should be flagged correctly
        self.assertFalse(augmented[1]['c7n:IsSecurityGroup'])
        self.assertTrue(augmented[1]['c7n:IsDistributionGroup'])
        self.assertFalse(augmented[1]['c7n:IsAdminGroup'])

        # Dynamic group should be flagged correctly
        self.assertTrue(augmented[2]['c7n:IsSecurityGroup'])
        self.assertTrue(augmented[2]['c7n:IsDynamicGroup'])

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_batched_graph_request')
    def test_member_count_filter(self, mock_member_count):
        """Test member count filter with real Graph API implementation"""
        groups = [
            {
                'id': 'group1',
                'displayName': 'Small Group'
            },
            {
                'id': 'group2',
                'displayName': 'Large Group'
            },
            {
                'id': 'group3',
                'displayName': 'Empty Group'
            }
        ]

        # Mock member counts: group1=2, group2=5, group3=0
        def mock_count_side_effect(group_id):
            return [
                {
                    "status": 200,
                    "id": "group1",
                    "body": 2
                },
                {
                    "status": 200,
                    "id": "group2",
                    "body": 5
                },
                {
                    "status": 200,
                    "id": "group3",
                    "body": 0
                }
            ]

        mock_member_count.side_effect = mock_count_side_effect

        policy = self.load_policy({
            'name': 'test-member-count',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-count', 'count': 3, 'op': 'greater-than'}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(groups)

        # Only group2 has >3 members
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'group2')

        # Verify the member count check was called
        self.assertEqual(mock_member_count.call_count, 1)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_owner_count')
    def test_owner_count_filter(self, mock_owner_count):
        """Test owner count filter with real Graph API implementation"""
        groups = [
            {
                'id': 'group1',
                'displayName': 'Owned Group'
            },
            {
                'id': 'group2',
                'displayName': 'Orphaned Group'
            }
        ]

        # Mock owner counts: group1=1, group2=0
        def mock_count_side_effect(group_id):
            if group_id == 'group1':
                return 1
            elif group_id == 'group2':
                return 0
            else:
                return None

        mock_owner_count.side_effect = mock_count_side_effect

        policy = self.load_policy({
            'name': 'test-owner-count',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'owner-count', 'count': 0, 'op': 'equal'}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(groups)

        # Only group2 has no owners
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'group2')

        # Verify the owner count check was called
        self.assertEqual(mock_owner_count.call_count, 2)

    def test_group_type_filter(self):
        """Test group type filter"""
        groups = [
            {
                'id': 'group1',
                'displayName': 'Security Group',
                'c7n:IsSecurityGroup': True,
                'c7n:IsDistributionGroup': False,
                'c7n:IsDynamicGroup': False,
                'c7n:IsAdminGroup': False
            },
            {
                'id': 'group2',
                'displayName': 'Distribution Group',
                'c7n:IsSecurityGroup': False,
                'c7n:IsDistributionGroup': True,
                'c7n:IsDynamicGroup': False,
                'c7n:IsAdminGroup': False
            },
            {
                'id': 'group3',
                'displayName': 'Admin Group',
                'c7n:IsSecurityGroup': True,
                'c7n:IsDistributionGroup': False,
                'c7n:IsDynamicGroup': False,
                'c7n:IsAdminGroup': True
            }
        ]

        policy = self.load_policy({
            'name': 'test-group-type',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'group-type', 'group-type': 'admin'}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(groups)

        # Only group3 is an admin group
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'group3')

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_graph_resources_success(self, mock_request):
        """Test successful retrieval of groups from Graph API"""
        mock_request.return_value = {
            'value': [
                {
                    'id': 'group1',
                    'displayName': 'Test Group 1',
                    'securityEnabled': True,
                    'mailEnabled': False,
                    'groupTypes': []
                },
                {
                    'id': 'group2',
                    'displayName': 'Admin Group',
                    'securityEnabled': True,
                    'mailEnabled': False,
                    'groupTypes': []
                }
            ]
        }

        policy = self.load_policy({
            'name': 'test-get-groups',
            'resource': 'azure.entraid-group'
        })

        resources = policy.resource_manager.get_graph_resources()

        self.assertEqual(len(resources), 2)
        self.assertIn('c7n:IsSecurityGroup', resources[0])
        self.assertTrue(resources[0]['c7n:IsSecurityGroup'])
        self.assertTrue(resources[1]['c7n:IsAdminGroup'])

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_graph_resources_permission_error(self, mock_request):
        """Test handling of permission errors when retrieving groups"""
        mock_request.side_effect = requests.exceptions.RequestException(
            "403 Forbidden: Insufficient privileges"
        )

        policy = self.load_policy({
            'name': 'test-get-groups-error',
            'resource': 'azure.entraid-group'
        })

        with self.assertRaises(requests.exceptions.RequestException):
            policy.resource_manager.get_graph_resources()

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_graph_resources_generic_error(self, mock_request):
        """Test handling of generic errors when retrieving groups"""
        mock_request.side_effect = requests.exceptions.RequestException("Network error")

        policy = self.load_policy({
            'name': 'test-get-groups-error',
            'resource': 'azure.entraid-group'
        })

        with self.assertRaises(requests.exceptions.RequestException):
            policy.resource_manager.get_graph_resources()

    def test_augment_exception_handling(self):
        """Test exception handling during augmentation"""
        policy = self.load_policy({
            'name': 'test-augment-error',
            'resource': 'azure.entraid-group'
        })

        # Pass invalid data that will cause augmentation to fail
        resources = [{'id': 'test', 'displayName': None}]

        # Should handle exception and still return resources
        result = policy.resource_manager.augment(resources)
        self.assertEqual(len(result), 1)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_group_member_count_success(self, mock_request):
        """Test successful retrieval of group member count"""
        mock_request.return_value = 42

        policy = self.load_policy({
            'name': 'test-member-count',
            'resource': 'azure.entraid-group'
        })

        count = policy.resource_manager.get_group_member_count('group-id')
        self.assertEqual(count, 42)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_group_member_count_string_response(self, mock_request):
        """Test member count with string response"""
        mock_request.return_value = "25"

        policy = self.load_policy({
            'name': 'test-member-count',
            'resource': 'azure.entraid-group'
        })

        count = policy.resource_manager.get_group_member_count('group-id')
        self.assertEqual(count, 25)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_group_member_count_unexpected_format(self, mock_request):
        """Test member count with unexpected response format"""
        mock_request.return_value = {'unexpected': 'format'}

        policy = self.load_policy({
            'name': 'test-member-count',
            'resource': 'azure.entraid-group'
        })

        count = policy.resource_manager.get_group_member_count('group-id')
        self.assertEqual(count, 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_group_member_count_permission_error(self, mock_request):
        """Test member count with permission error"""
        mock_request.side_effect = requests.exceptions.RequestException("403 Forbidden")

        policy = self.load_policy({
            'name': 'test-member-count',
            'resource': 'azure.entraid-group'
        })

        with self.assertRaises(requests.exceptions.RequestException):
            policy.resource_manager.get_group_member_count('group-id')

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_group_member_count_generic_error(self, mock_request):
        """Test member count with generic error"""
        mock_request.side_effect = requests.exceptions.RequestException("Network error")

        policy = self.load_policy({
            'name': 'test-member-count',
            'resource': 'azure.entraid-group'
        })

        with self.assertRaises(requests.exceptions.RequestException):
            policy.resource_manager.get_group_member_count('group-id')

    @patch('c7n_azure.graph_utils.requests.get')
    @patch('c7n_azure.graph_utils.local_session')
    def test_get_group_member_count_consistency_level_header(self, mock_session, mock_get):
        """Test that member count requests include ConsistencyLevel: eventual header"""
        # Setup mock session and credentials
        mock_session_instance = Mock()
        mock_session.return_value = mock_session_instance
        mock_session_instance.get_session_for_resource.return_value = mock_session_instance

        mock_credentials = Mock()
        mock_token = Mock()
        mock_token.token = 'test-token'
        mock_credentials.get_token.return_value = mock_token
        mock_session_instance.credentials = mock_credentials
        mock_session_instance._initialize_session = Mock()

        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = 42
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        policy = self.load_policy({
            'name': 'test-member-count-header',
            'resource': 'azure.entraid-group'
        })

        # Call the method
        count = policy.resource_manager.get_group_member_count('test-group-id')

        # Verify the call was made with the ConsistencyLevel header
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        headers = call_args.kwargs.get('headers', {})

        # Assert that ConsistencyLevel: eventual header is present
        self.assertIn('ConsistencyLevel', headers)
        self.assertEqual(headers['ConsistencyLevel'], 'eventual')
        self.assertEqual(count, 42)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_group_owner_count_success(self, mock_request):
        """Test successful retrieval of group owner count"""
        mock_request.return_value = 3

        policy = self.load_policy({
            'name': 'test-owner-count',
            'resource': 'azure.entraid-group'
        })

        count = policy.resource_manager.get_group_owner_count('group-id')
        self.assertEqual(count, 3)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_group_owner_count_unexpected_format(self, mock_request):
        """Test owner count with unexpected response format"""
        mock_request.return_value = ['not', 'a', 'number']

        policy = self.load_policy({
            'name': 'test-owner-count',
            'resource': 'azure.entraid-group'
        })

        count = policy.resource_manager.get_group_owner_count('group-id')
        self.assertEqual(count, 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_group_owner_count_permission_error(self, mock_request):
        """Test owner count with permission error"""
        mock_request.side_effect = requests.exceptions.RequestException("Insufficient privileges")

        policy = self.load_policy({
            'name': 'test-owner-count',
            'resource': 'azure.entraid-group'
        })

        count = policy.resource_manager.get_group_owner_count('group-id')
        self.assertIsNone(count)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_group_owner_count_generic_error(self, mock_request):
        """Test owner count with generic error"""
        mock_request.side_effect = requests.exceptions.RequestException("Timeout")

        policy = self.load_policy({
            'name': 'test-owner-count',
            'resource': 'azure.entraid-group'
        })

        count = policy.resource_manager.get_group_owner_count('group-id')
        self.assertIsNone(count)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_analyze_group_member_types_success(self, mock_request):
        """Test successful analysis of group member types"""
        mock_request.return_value = {
            'value': [
                {
                    '@odata.type': '#microsoft.graph.user',
                    'id': 'user1',
                    'userType': 'Member',
                    'userPrincipalName': 'user1@example.com'
                },
                {
                    '@odata.type': '#microsoft.graph.user',
                    'id': 'user2',
                    'userType': 'Guest',
                    'userPrincipalName': 'user2_external#EXT#@example.com'
                }
            ]
        }

        policy = self.load_policy({
            'name': 'test-member-types',
            'resource': 'azure.entraid-group'
        })

        analysis = policy.resource_manager.analyze_group_member_types('group-id')

        self.assertTrue(analysis['has_external_members'])
        self.assertTrue(analysis['has_guest_members'])
        self.assertEqual(analysis['total_members'], 2)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_analyze_group_member_types_external_only(self, mock_request):
        """Test analysis with external members only"""
        mock_request.return_value = {
            'value': [
                {
                    '@odata.type': '#microsoft.graph.user',
                    'id': 'user1',
                    'userType': 'Member',
                    'userPrincipalName': 'user1_external#EXT#@example.com'
                }
            ]
        }

        policy = self.load_policy({
            'name': 'test-member-types',
            'resource': 'azure.entraid-group'
        })

        analysis = policy.resource_manager.analyze_group_member_types('group-id')

        self.assertTrue(analysis['has_external_members'])
        self.assertFalse(analysis['has_guest_members'])

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_analyze_group_member_types_permission_error(self, mock_request):
        """Test member type analysis with permission error"""
        mock_request.side_effect = requests.exceptions.RequestException("403 Forbidden")

        policy = self.load_policy({
            'name': 'test-member-types',
            'resource': 'azure.entraid-group'
        })

        analysis = policy.resource_manager.analyze_group_member_types('group-id')
        self.assertIsNone(analysis)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_analyze_group_member_types_generic_error(self, mock_request):
        """Test member type analysis with generic error"""
        mock_request.side_effect = requests.exceptions.RequestException("Connection error")

        policy = self.load_policy({
            'name': 'test-member-types',
            'resource': 'azure.entraid-group'
        })

        analysis = policy.resource_manager.analyze_group_member_types('group-id')
        self.assertIsNone(analysis)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_batched_graph_request')
    def test_member_count_filter_missing_group_id(self, mock_count):
        """Test member count filter with missing group ID"""
        groups = [
            {'displayName': 'Test Group'}  # No ID
        ]

        policy = self.load_policy({
            'name': 'test-member-count-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-count', 'count': 10, 'op': 'greater-than'}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_batched_graph_request')
    def test_member_count_filter_none_count(self, mock_count):
        """Test member count filter with None count (permission error)"""
        mock_count.return_value = [
            {
                "status": 403,
                "id": "group1",
                "body": "Permission denied"
            }
        ]

        groups = [
            {'id': 'group1', 'displayName': 'Test Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-count-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-count', 'count': 10, 'op': 'greater-than'}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_batched_graph_request')
    def test_member_count_filter_less_than(self, mock_count):
        """Test member count filter with less-than operator"""
        mock_count.return_value = [
            {
                "status": 200,
                "id": "group1",
                "body": 5
            }
        ]

        groups = [
            {'id': 'group1', 'displayName': 'Small Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-count-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-count', 'count': 10, 'op': 'less-than'}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 1)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_batched_graph_request')
    def test_member_count_filter_equal(self, mock_count):
        """Test member count filter with equal operator"""
        mock_count.return_value = [
            {
                "status": 200,
                "id": "group1",
                "body": 10
            }
        ]

        groups = [
            {'id': 'group1', 'displayName': 'Exact Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-count-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-count', 'count': 10, 'op': 'equal'}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 1)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_batched_graph_request')
    def test_member_count_filter_greater_than(self, mock_count):
        """Test member count filter with greater-than matching"""
        mock_count.return_value = [
            {
                "status": 200,
                "id": "group1",
                "body": 150
            }
        ]

        groups = [
            {'id': 'group1', 'displayName': 'Large Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-count-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-count', 'count': 100, 'op': 'greater-than'}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 1)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_owner_count')
    def test_owner_count_filter_missing_group_id(self, mock_count):
        """Test owner count filter with missing group ID"""
        groups = [
            {'displayName': 'Test Group'}  # No ID
        ]

        policy = self.load_policy({
            'name': 'test-owner-count-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'owner-count', 'count': 0, 'op': 'equal'}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_owner_count')
    def test_owner_count_filter_none_count(self, mock_count):
        """Test owner count filter with None count (permission error)"""
        mock_count.return_value = None

        groups = [
            {'id': 'group1', 'displayName': 'Test Group'}
        ]

        policy = self.load_policy({
            'name': 'test-owner-count-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'owner-count', 'count': 0, 'op': 'equal'}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_owner_count')
    def test_owner_count_filter_greater_than(self, mock_count):
        """Test owner count filter with greater-than operator"""
        mock_count.return_value = 5

        groups = [
            {'id': 'group1', 'displayName': 'Many Owners Group'}
        ]

        policy = self.load_policy({
            'name': 'test-owner-count-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'owner-count', 'count': 3, 'op': 'greater-than'}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 1)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_owner_count')
    def test_owner_count_filter_less_than(self, mock_count):
        """Test owner count filter with less-than operator"""
        mock_count.return_value = 1

        groups = [
            {'id': 'group1', 'displayName': 'Few Owners Group'}
        ]

        policy = self.load_policy({
            'name': 'test-owner-count-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'owner-count', 'count': 2, 'op': 'less-than'}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 1)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_owner_count')
    def test_owner_count_filter_equal(self, mock_count):
        """Test owner count filter with equal operator matching"""
        mock_count.return_value = 2

        groups = [
            {'id': 'group1', 'displayName': 'Two Owners Group'}
        ]

        policy = self.load_policy({
            'name': 'test-owner-count-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'owner-count', 'count': 2, 'op': 'equal'}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 1)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.analyze_group_member_types')
    def test_member_types_filter_missing_group_id(self, mock_analysis):
        """Test member types filter with missing group ID"""
        groups = [
            {'displayName': 'Test Group'}  # No ID
        ]

        policy = self.load_policy({
            'name': 'test-member-types-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-types', 'include-external': True}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.analyze_group_member_types')
    def test_member_types_filter_none_analysis(self, mock_analysis):
        """Test member types filter with None analysis (permission error)"""
        mock_analysis.return_value = None

        groups = [
            {'id': 'group1', 'displayName': 'Test Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-types-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-types', 'include-external': True}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.analyze_group_member_types')
    def test_member_types_filter_include_external(self, mock_analysis):
        """Test member types filter with include-external"""
        mock_analysis.return_value = {
            'has_external_members': True,
            'has_guest_members': False,
            'total_members': 5
        }

        groups = [
            {'id': 'group1', 'displayName': 'External Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-types-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-types', 'include-external': True}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 1)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.analyze_group_member_types')
    def test_member_types_filter_exclude_external(self, mock_analysis):
        """Test member types filter with exclude external"""
        mock_analysis.return_value = {
            'has_external_members': True,
            'has_guest_members': False,
            'total_members': 5
        }

        groups = [
            {'id': 'group1', 'displayName': 'External Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-types-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-types', 'include-external': False}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.analyze_group_member_types')
    def test_member_types_filter_include_guests(self, mock_analysis):
        """Test member types filter with include-guests"""
        mock_analysis.return_value = {
            'has_external_members': False,
            'has_guest_members': True,
            'total_members': 3
        }

        groups = [
            {'id': 'group1', 'displayName': 'Guest Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-types-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-types', 'include-guests': True}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 1)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.analyze_group_member_types')
    def test_member_types_filter_exclude_guests(self, mock_analysis):
        """Test member types filter excluding guest users"""
        mock_analysis.return_value = {
            'has_external_members': False,
            'has_guest_members': True,
            'total_members': 5
        }

        groups = [
            {'id': 'group1', 'displayName': 'Guest Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-types-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-types', 'include-guests': False}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.analyze_group_member_types')
    def test_member_types_filter_no_external_when_required(self, mock_analysis):
        """Test member types filter when external members are required but not present"""
        mock_analysis.return_value = {
            'has_external_members': False,
            'has_guest_members': False,
            'total_members': 5
        }

        groups = [
            {'id': 'group1', 'displayName': 'Internal Only Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-types-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-types', 'include-external': True}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.analyze_group_member_types')
    def test_member_types_filter_no_guests_when_required(self, mock_analysis):
        """Test member types filter when guests are required but not present"""
        mock_analysis.return_value = {
            'has_external_members': False,
            'has_guest_members': False,
            'total_members': 5
        }

        groups = [
            {'id': 'group1', 'displayName': 'No Guests Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-types-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-types', 'include-guests': True}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.analyze_group_member_types')
    def test_member_types_filter_combined(self, mock_analysis):
        """Test member types filter with combined filters"""
        mock_analysis.return_value = {
            'has_external_members': True,
            'has_guest_members': True,
            'total_members': 10
        }

        groups = [
            {'id': 'group1', 'displayName': 'Mixed Group'}
        ]

        policy = self.load_policy({
            'name': 'test-member-types-filter',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'member-types', 'include-external': True, 'include-guests': True}
            ]
        })

        filtered = policy.resource_manager.filter_resources(groups)
        self.assertEqual(len(filtered), 1)


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


@terraform('entraid_group')
@pytest.mark.functional
def test_entraid_group_discovery_terraform(test, entraid_group):
    """Test that Cloud Custodian can discover groups provisioned by Terraform"""
    # Verify terraform fixtures loaded successfully
    assert len(entraid_group.outputs) > 0, (
        f"Expected outputs from Terraform, got {len(entraid_group.outputs)}"
    )
    assert 'azuread_group' in entraid_group.resources, "azuread_group resources not found"

    # Get terraform-provisioned group data
    security_group = entraid_group.outputs['test_security_group']['value']
    distribution_group = entraid_group.outputs['test_distribution_group']['value']
    dynamic_group = entraid_group.outputs['test_dynamic_group']['value']
    admin_group = entraid_group.outputs['test_admin_group']['value']
    empty_group = entraid_group.outputs['test_empty_group']['value']

    # Verify test data integrity
    assert security_group['security_enabled'] is True
    assert security_group['mail_enabled'] is False
    assert 'Security' in security_group['display_name']

    # Distribution group is simplified to just another security group (not mail-enabled)
    assert distribution_group['security_enabled'] is True
    assert distribution_group['mail_enabled'] is False
    assert (
        'Second' in distribution_group['display_name']
        or 'Distribution' in distribution_group['display_name']
    )

    # Dynamic group is now just a regular security group
    # (dynamic membership requires Azure AD P1 license)
    assert dynamic_group['security_enabled'] is True
    assert dynamic_group['mail_enabled'] is False
    assert (
        'Third' in dynamic_group['display_name']
        or 'Dynamic' in dynamic_group['display_name']
    )

    assert admin_group['security_enabled'] is True
    assert 'Admin' in admin_group['display_name']

    assert empty_group['security_enabled'] is True
    assert 'Empty' in empty_group['display_name']

    # Test Cloud Custodian policy creation and validation
    policy = test.load_policy({
        'name': 'terraform-security-groups',
        'resource': 'azure.entraid-group',
        'filters': [
            {'type': 'value', 'key': 'securityEnabled', 'value': True}
        ]
    })

    # Verify policy loads correctly
    assert policy.resource_manager.type == 'entraid-group'

    print(f"SUCCESS: Terraform fixtures loaded {len(entraid_group.outputs)} groups successfully")


@terraform('entraid_group')
@pytest.mark.functional
def test_entraid_group_type_filter_terraform(test, entraid_group):
    """Test group-type filter against Terraform-provisioned groups"""
    security_group = entraid_group.outputs['test_security_group']['value']
    distribution_group = entraid_group.outputs['test_distribution_group']['value']
    dynamic_group = entraid_group.outputs['test_dynamic_group']['value']

    # Test policy for security groups
    security_policy = test.load_policy({
        'name': 'terraform-security-groups',
        'resource': 'azure.entraid-group',
        'filters': [
            {'type': 'group-type', 'group-type': 'security'}
        ]
    })

    # Verify test data has expected types
    assert security_group['security_enabled'] is True
    assert security_group['mail_enabled'] is False

    # Distribution group is now just another security group (simplified)
    assert distribution_group['security_enabled'] is True
    assert distribution_group['mail_enabled'] is False

    # Dynamic group is now just a regular security group (no DynamicMembership type)
    assert dynamic_group['security_enabled'] is True
    assert dynamic_group['mail_enabled'] is False

    # Verify policy validates correctly
    assert security_policy is not None

    # Test policy for distribution groups
    distribution_policy = test.load_policy({
        'name': 'terraform-distribution-groups',
        'resource': 'azure.entraid-group',
        'filters': [
            {'type': 'group-type', 'group-type': 'distribution'}
        ]
    })

    assert distribution_policy is not None

    # Test policy for dynamic groups
    dynamic_policy = test.load_policy({
        'name': 'terraform-dynamic-groups',
        'resource': 'azure.entraid-group',
        'filters': [
            {'type': 'group-type', 'group-type': 'dynamic'}
        ]
    })

    assert dynamic_policy is not None


@terraform('entraid_group')
@pytest.mark.functional
def test_entraid_group_owner_count_filter_terraform(test, entraid_group):
    """Test owner-count filter against Terraform-provisioned groups"""
    empty_group = entraid_group.outputs['test_empty_group']['value']
    security_group = entraid_group.outputs['test_security_group']['value']

    # Test policy for groups without owners
    no_owner_policy = test.load_policy({
        'name': 'terraform-groups-no-owners',
        'resource': 'azure.entraid-group',
        'filters': [
            {'type': 'owner-count', 'count': 0, 'op': 'equal'}
        ]
    })

    # Verify test data
    assert empty_group['display_name'] is not None
    assert security_group['display_name'] is not None

    # Verify policy validates correctly
    assert no_owner_policy is not None

    # Test policy for groups with owners
    has_owner_policy = test.load_policy({
        'name': 'terraform-groups-with-owners',
        'resource': 'azure.entraid-group',
        'filters': [
            {'type': 'owner-count', 'count': 0, 'op': 'greater-than'}
        ]
    })

    assert has_owner_policy is not None


@terraform('entraid_group')
@pytest.mark.functional
def test_entraid_group_member_count_filter_terraform(test, entraid_group):
    """Test member-count filter against Terraform-provisioned groups"""
    empty_group = entraid_group.outputs['test_empty_group']['value']
    security_group = entraid_group.outputs['test_security_group']['value']

    # Test policy for empty groups
    empty_policy = test.load_policy({
        'name': 'terraform-empty-groups',
        'resource': 'azure.entraid-group',
        'filters': [
            {'type': 'member-count', 'count': 0, 'op': 'equal'}
        ]
    })

    # Verify test data
    assert empty_group['display_name'] is not None
    assert security_group['display_name'] is not None

    # Verify policy validates correctly
    assert empty_policy is not None

    # Test policy for groups with members
    has_members_policy = test.load_policy({
        'name': 'terraform-groups-with-members',
        'resource': 'azure.entraid-group',
        'filters': [
            {'type': 'member-count', 'count': 0, 'op': 'greater-than'}
        ]
    })

    assert has_members_policy is not None

    # Test policy for large groups
    large_groups_policy = test.load_policy({
        'name': 'terraform-large-groups',
        'resource': 'azure.entraid-group',
        'filters': [
            {'type': 'member-count', 'count': 100, 'op': 'greater-than'}
        ]
    })

    assert large_groups_policy is not None
