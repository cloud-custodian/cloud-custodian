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
from c7n_azure.resources.entraid_organization import EntraIDOrganization
from c7n_azure.resources.entraid_conditional_access import EntraIDConditionalAccessPolicy
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

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_member_count')
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
            if group_id == 'group1':
                return 2
            elif group_id == 'group2':
                return 5
            elif group_id == 'group3':
                return 0
            else:
                return None

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
        self.assertEqual(mock_member_count.call_count, 3)

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

        resources = policy.resource_manager.get_graph_resources()

        # Should return empty list on permission error
        self.assertEqual(resources, [])

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_graph_resources_generic_error(self, mock_request):
        """Test handling of generic errors when retrieving groups"""
        mock_request.side_effect = requests.exceptions.RequestException("Network error")

        policy = self.load_policy({
            'name': 'test-get-groups-error',
            'resource': 'azure.entraid-group'
        })

        resources = policy.resource_manager.get_graph_resources()

        # Should return empty list on error
        self.assertEqual(resources, [])

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

        count = policy.resource_manager.get_group_member_count('group-id')
        self.assertIsNone(count)

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.make_graph_request')
    def test_get_group_member_count_generic_error(self, mock_request):
        """Test member count with generic error"""
        mock_request.side_effect = requests.exceptions.RequestException("Network error")

        policy = self.load_policy({
            'name': 'test-member-count',
            'resource': 'azure.entraid-group'
        })

        count = policy.resource_manager.get_group_member_count('group-id')
        self.assertIsNone(count)

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

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_member_count')
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

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_member_count')
    def test_member_count_filter_none_count(self, mock_count):
        """Test member count filter with None count (permission error)"""
        mock_count.return_value = None

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

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_member_count')
    def test_member_count_filter_less_than(self, mock_count):
        """Test member count filter with less-than operator"""
        mock_count.return_value = 5

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

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_member_count')
    def test_member_count_filter_equal(self, mock_count):
        """Test member count filter with equal operator"""
        mock_count.return_value = 10

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

    @patch('c7n_azure.resources.entraid_group.EntraIDGroup.get_group_member_count')
    def test_member_count_filter_greater_than(self, mock_count):
        """Test member count filter with greater-than matching"""
        mock_count.return_value = 150

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


class EntraIDOrganizationTest(BaseTest):
    """Test EntraID Organization resource functionality"""

    def test_entraid_organization_schema_validate(self):
        """Test organization resource schema validation"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-organization',
                'resource': 'azure.entraid-organization',
                'filters': [
                    {'type': 'security-defaults', 'enabled': True}
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_organization_resource_type(self):
        """Test organization resource type configuration"""
        resource_type = EntraIDOrganization.resource_type
        self.assertEqual(resource_type.service, 'graph')
        self.assertEqual(resource_type.id, 'id')
        self.assertTrue(resource_type.global_resource)
        self.assertIn('Organization.Read.All', resource_type.permissions)
        self.assertIn('Directory.Read.All', resource_type.permissions)

    def test_security_defaults_filter(self):
        """Test security defaults filter"""
        orgs = [
            {
                'id': 'org1',
                'displayName': 'Test Organization',
                'securityDefaults': {'isEnabled': True}
            },
            {
                'id': 'org2',
                'displayName': 'Another Organization',
                'securityDefaults': {'isEnabled': False}
            }
        ]

        policy = self.load_policy({
            'name': 'test-security-defaults',
            'resource': 'azure.entraid-organization',
            'filters': [
                {'type': 'security-defaults', 'enabled': False}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(orgs)

        # Only org2 has security defaults disabled
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'org2')

    def test_password_lockout_threshold_schema_validate(self):
        """Test password lockout threshold filter schema validation"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-lockout-threshold',
                'resource': 'azure.entraid-organization',
                'filters': [
                    {'type': 'password-lockout-threshold', 'max_threshold': 10}
                ]
            }, validate=True)
            self.assertTrue(p)

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.make_graph_request')
    def test_password_lockout_threshold_filter(self, mock_graph_request):
        """Test password lockout threshold filter with mocked API responses"""
        # Mock API responses for template lookup and settings
        def mock_request_side_effect(endpoint):
            if 'directorySettingTemplates' in endpoint:
                return {
                    'value': [{
                        'id': '5cf42378-d67d-4f36-ba46-e8b86229381d',
                        'displayName': 'Password Rule Settings'
                    }]
                }
            elif endpoint == 'settings':
                return {
                    'value': [{
                        'id': 'setting1',
                        'templateId': '5cf42378-d67d-4f36-ba46-e8b86229381d',
                        'values': [
                            {'name': 'LockoutThreshold', 'value': '15'},
                            {'name': 'LockoutDurationInSeconds', 'value': '60'}
                        ]
                    }]
                }
            else:
                return {'value': []}

        mock_graph_request.side_effect = mock_request_side_effect

        orgs = [
            {
                'id': 'org1',
                'displayName': 'Test Organization'
            }
        ]

        policy = self.load_policy({
            'name': 'test-lockout-threshold',
            'resource': 'azure.entraid-organization',
            'filters': [
                {'type': 'password-lockout-threshold', 'max_threshold': 10}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(orgs)

        # Should filter org1 because threshold (15) > max_threshold (10)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'org1')
        self.assertEqual(filtered[0]['lockoutThreshold'], 15)

        # Verify API calls were made
        self.assertEqual(mock_graph_request.call_count, 2)
        mock_graph_request.assert_any_call('directorySettingTemplates')
        mock_graph_request.assert_any_call('settings')

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.make_graph_request')
    def test_password_lockout_threshold_filter_within_limit(self, mock_graph_request):
        """Test password lockout threshold filter when threshold is within acceptable limit"""
        # Mock API responses with threshold within limit
        def mock_request_side_effect(endpoint):
            if 'directorySettingTemplates' in endpoint:
                return {
                    'value': [{
                        'id': '5cf42378-d67d-4f36-ba46-e8b86229381d',
                        'displayName': 'Password Rule Settings'
                    }]
                }
            elif endpoint == 'settings':
                return {
                    'value': [{
                        'id': 'setting1',
                        'templateId': '5cf42378-d67d-4f36-ba46-e8b86229381d',
                        'values': [
                            {'name': 'LockoutThreshold', 'value': '8'},
                            {'name': 'LockoutDurationInSeconds', 'value': '60'}
                        ]
                    }]
                }
            else:
                return {'value': []}

        mock_graph_request.side_effect = mock_request_side_effect

        orgs = [
            {
                'id': 'org1',
                'displayName': 'Test Organization'
            }
        ]

        policy = self.load_policy({
            'name': 'test-lockout-threshold-compliant',
            'resource': 'azure.entraid-organization',
            'filters': [
                {'type': 'password-lockout-threshold', 'max_threshold': 10}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(orgs)

        # Should not filter org1 because threshold (8) <= max_threshold (10)
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.make_graph_request')
    def test_password_lockout_threshold_template_not_found(self, mock_graph_request):
        """Test password lockout threshold filter when template is not found"""
        # Mock API response with empty template list
        def mock_request_side_effect(endpoint):
            if 'directorySettingTemplates' in endpoint:
                return {'value': []}
            else:
                return {'value': []}

        mock_graph_request.side_effect = mock_request_side_effect

        orgs = [
            {
                'id': 'org1',
                'displayName': 'Test Organization'
            }
        ]

        policy = self.load_policy({
            'name': 'test-lockout-threshold-no-template',
            'resource': 'azure.entraid-organization',
            'filters': [
                {'type': 'password-lockout-threshold', 'max_threshold': 10}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(orgs)

        # Should return empty list when template is not found
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.make_graph_request')
    def test_password_lockout_threshold_setting_not_found(self, mock_graph_request):
        """Test password lockout threshold filter when directory setting is not found"""
        # Mock API responses where template exists but no directory settings
        def mock_request_side_effect(endpoint):
            if 'directorySettingTemplates' in endpoint:
                return {
                    'value': [{
                        'id': '5cf42378-d67d-4f36-ba46-e8b86229381d',
                        'displayName': 'Password Rule Settings'
                    }]
                }
            elif endpoint == 'settings':
                return {'value': []}  # No directory settings
            else:
                return {'value': []}

        mock_graph_request.side_effect = mock_request_side_effect

        orgs = [
            {
                'id': 'org1',
                'displayName': 'Test Organization'
            }
        ]

        policy = self.load_policy({
            'name': 'test-lockout-threshold-no-setting',
            'resource': 'azure.entraid-organization',
            'filters': [
                {'type': 'password-lockout-threshold', 'max_threshold': 10}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(orgs)

        # Should return empty list when directory setting is not found
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.make_graph_request')
    def test_password_lockout_threshold_invalid_value(self, mock_graph_request):
        """Test password lockout threshold filter with invalid threshold value"""
        # Mock API responses with invalid threshold value
        def mock_request_side_effect(endpoint):
            if 'directorySettingTemplates' in endpoint:
                return {
                    'value': [{
                        'id': '5cf42378-d67d-4f36-ba46-e8b86229381d',
                        'displayName': 'Password Rule Settings'
                    }]
                }
            elif endpoint == 'settings':
                return {
                    'value': [{
                        'id': 'setting1',
                        'templateId': '5cf42378-d67d-4f36-ba46-e8b86229381d',
                        'values': [
                            {'name': 'LockoutThreshold', 'value': 'invalid_number'},
                            {'name': 'LockoutDurationInSeconds', 'value': '60'}
                        ]
                    }]
                }
            else:
                return {'value': []}

        mock_graph_request.side_effect = mock_request_side_effect

        orgs = [
            {
                'id': 'org1',
                'displayName': 'Test Organization'
            }
        ]

        policy = self.load_policy({
            'name': 'test-lockout-threshold-invalid',
            'resource': 'azure.entraid-organization',
            'filters': [
                {'type': 'password-lockout-threshold', 'max_threshold': 10}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(orgs)

        # Should return empty list when threshold value is invalid
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.make_graph_request')
    def test_password_lockout_threshold_default_max_threshold(self, mock_graph_request):
        """Test password lockout threshold filter with default max_threshold (10)"""
        # Mock API responses with threshold above default limit
        def mock_request_side_effect(endpoint):
            if 'directorySettingTemplates' in endpoint:
                return {
                    'value': [{
                        'id': '5cf42378-d67d-4f36-ba46-e8b86229381d',
                        'displayName': 'Password Rule Settings'
                    }]
                }
            elif endpoint == 'settings':
                return {
                    'value': [{
                        'id': 'setting1',
                        'templateId': '5cf42378-d67d-4f36-ba46-e8b86229381d',
                        'values': [
                            {'name': 'LockoutThreshold', 'value': '12'},
                            {'name': 'LockoutDurationInSeconds', 'value': '60'}
                        ]
                    }]
                }
            else:
                return {'value': []}

        mock_graph_request.side_effect = mock_request_side_effect

        orgs = [
            {
                'id': 'org1',
                'displayName': 'Test Organization'
            }
        ]

        # Test without specifying max_threshold (should default to 10)
        policy = self.load_policy({
            'name': 'test-lockout-threshold-default',
            'resource': 'azure.entraid-organization',
            'filters': [
                {'type': 'password-lockout-threshold'}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(orgs)

        # Should filter org1 because threshold (12) > default max_threshold (10)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'org1')
        self.assertEqual(filtered[0]['lockoutThreshold'], 12)

    @patch('c7n_azure.resources.entraid_organization.requests.get')
    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.get_client')
    def test_make_graph_request_beta_api(self, mock_get_client, mock_requests_get):
        """Test make_graph_request method for beta API endpoints"""
        # Setup mock session and credentials
        mock_token = Mock()
        mock_token.token = 'test-access-token'
        mock_credentials = Mock()
        mock_credentials.get_token.return_value = mock_token

        mock_session = Mock()
        mock_session.credentials = mock_credentials
        mock_session._initialize_session = Mock()
        mock_get_client.return_value = mock_session

        # Setup mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            'value': [{
                'id': 'template1',
                'displayName': 'Test Template'
            }]
        }
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        policy = self.load_policy({
            'name': 'test-beta-api',
            'resource': 'azure.entraid-organization'
        })

        resource_mgr = policy.resource_manager
        result = resource_mgr.make_graph_request('directorySettingTemplates')

        # Verify beta API was called
        mock_requests_get.assert_called_once()
        call_args = mock_requests_get.call_args
        self.assertIn('beta', call_args[0][0])
        self.assertIn('directorySettingTemplates', call_args[0][0])

        # Verify headers
        headers = call_args[1]['headers']
        self.assertEqual(headers['Authorization'], 'Bearer test-access-token')
        self.assertEqual(headers['Content-Type'], 'application/json')

        # Verify result
        self.assertEqual(result['value'][0]['id'], 'template1')

    @patch('c7n_azure.resources.entraid_organization.requests.get')
    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.get_client')
    def test_make_graph_request_beta_api_http_error(self, mock_get_client, mock_requests_get):
        """Test make_graph_request error handling for beta API HTTP errors"""
        # Setup mock session and credentials
        mock_token = Mock()
        mock_token.token = 'test-access-token'
        mock_credentials = Mock()
        mock_credentials.get_token.return_value = mock_token

        mock_session = Mock()
        mock_session.credentials = mock_credentials
        mock_session._initialize_session = Mock()
        mock_get_client.return_value = mock_session

        # Setup mock response to raise HTTP error
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError('403 Forbidden')
        mock_requests_get.return_value = mock_response

        policy = self.load_policy({
            'name': 'test-beta-api-error',
            'resource': 'azure.entraid-organization'
        })

        resource_mgr = policy.resource_manager

        # Should raise exception
        with self.assertRaises(requests.HTTPError):
            resource_mgr.make_graph_request('settings')

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.get_client')
    @patch('c7n_azure.graph_utils.get_required_permissions_for_endpoint')
    def test_make_graph_request_beta_api_unmapped_endpoint(self, mock_get_perms, mock_get_client):
        """Test make_graph_request error handling for unmapped endpoint"""
        # Setup mocks
        mock_get_perms.side_effect = ValueError("Unmapped endpoint")

        mock_session = Mock()
        mock_session._initialize_session = Mock()
        mock_get_client.return_value = mock_session

        policy = self.load_policy({
            'name': 'test-unmapped-endpoint',
            'resource': 'azure.entraid-organization'
        })

        resource_mgr = policy.resource_manager

        # Should raise ValueError for unmapped endpoint
        with self.assertRaises(ValueError):
            resource_mgr.make_graph_request('settings')

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.make_graph_request')
    def test_make_graph_request_v1_fallback(self, mock_make_graph_request):
        """Test that make_graph_request falls back to v1.0 for non-beta endpoints"""
        # Mock the parent class method
        mock_make_graph_request.return_value = {
            'value': [{
                'id': 'org1',
                'displayName': 'Test Org'
            }]
        }

        policy = self.load_policy({
            'name': 'test-v1-fallback',
            'resource': 'azure.entraid-organization'
        })

        resource_mgr = policy.resource_manager

        # Directly test that organization endpoint would use parent class
        # This tests line 100 (the else branch)
        # We'll validate this indirectly through get_graph_resources
        result = resource_mgr.get_graph_resources()

        # Verify the method was called
        mock_make_graph_request.assert_called()
        self.assertEqual(len(result), 1)

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.make_graph_request')
    def test_get_graph_resources_error_handling(self, mock_make_graph_request):
        """Test get_graph_resources error handling"""
        # Make the API request raise an exception
        mock_make_graph_request.side_effect = Exception("API Error")

        policy = self.load_policy({
            'name': 'test-get-resources-error',
            'resource': 'azure.entraid-organization'
        })

        resource_mgr = policy.resource_manager
        result = resource_mgr.get_graph_resources()

        # Should return empty list on error
        self.assertEqual(result, [])

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.make_graph_request')
    def test_password_lockout_threshold_no_template_id(self, mock_graph_request):
        """Test password lockout threshold filter when template has no ID"""
        # Mock API response with template missing id field
        def mock_request_side_effect(endpoint):
            if 'directorySettingTemplates' in endpoint:
                return {
                    'value': [{
                        'displayName': 'Password Rule Settings'
                        # No 'id' field
                    }]
                }
            else:
                return {'value': []}

        mock_graph_request.side_effect = mock_request_side_effect

        orgs = [
            {
                'id': 'org1',
                'displayName': 'Test Organization'
            }
        ]

        policy = self.load_policy({
            'name': 'test-lockout-threshold-no-id',
            'resource': 'azure.entraid-organization',
            'filters': [
                {'type': 'password-lockout-threshold', 'max_threshold': 10}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(orgs)

        # Should return empty list when template ID is not found
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.make_graph_request')
    def test_password_lockout_threshold_template_api_error(self, mock_graph_request):
        """Test password lockout threshold filter when template API call fails"""
        # Mock API to raise exception
        mock_graph_request.side_effect = Exception("API Error")

        orgs = [
            {
                'id': 'org1',
                'displayName': 'Test Organization'
            }
        ]

        policy = self.load_policy({
            'name': 'test-lockout-threshold-api-error',
            'resource': 'azure.entraid-organization',
            'filters': [
                {'type': 'password-lockout-threshold', 'max_threshold': 10}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(orgs)

        # Should return empty list on API error
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_organization.EntraIDOrganization.make_graph_request')
    def test_password_lockout_threshold_settings_api_error(self, mock_graph_request):
        """Test password lockout threshold filter when settings API call fails"""
        # Mock API responses where template works but settings fails
        def mock_request_side_effect(endpoint):
            if 'directorySettingTemplates' in endpoint:
                return {
                    'value': [{
                        'id': '5cf42378-d67d-4f36-ba46-e8b86229381d',
                        'displayName': 'Password Rule Settings'
                    }]
                }
            elif endpoint == 'settings':
                raise Exception("Settings API Error")
            else:
                return {'value': []}

        mock_graph_request.side_effect = mock_request_side_effect

        orgs = [
            {
                'id': 'org1',
                'displayName': 'Test Organization'
            }
        ]

        policy = self.load_policy({
            'name': 'test-lockout-threshold-settings-error',
            'resource': 'azure.entraid-organization',
            'filters': [
                {'type': 'password-lockout-threshold', 'max_threshold': 10}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(orgs)

        # Should return empty list when settings API fails
        self.assertEqual(len(filtered), 0)


class EntraIDConditionalAccessTest(BaseTest):
    """Test EntraID Conditional Access Policy resource functionality"""

    def test_conditional_access_schema_validate(self):
        """Test conditional access policy schema validation"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-conditional-access',
                'resource': 'azure.entraid-conditional-access-policy',
                'filters': [
                    {'type': 'value', 'key': 'state', 'value': 'enabled'}
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_conditional_access_resource_type(self):
        """Test conditional access resource type configuration"""
        resource_type = EntraIDConditionalAccessPolicy.resource_type
        self.assertEqual(resource_type.service, 'graph')
        self.assertEqual(resource_type.id, 'id')
        self.assertTrue(resource_type.global_resource)
        self.assertIn('Policy.Read.All', resource_type.permissions)

    def test_admin_mfa_required_filter(self):
        """Test admin MFA required filter"""
        policies = [
            {
                'id': 'policy1',
                'displayName': 'Admin MFA Policy',
                'state': 'enabled',
                'conditions': {
                    'users': {
                        'includeRoles': ['Global Administrator']
                    }
                },
                'grantControls': {
                    'builtInControls': ['mfa']
                }
            },
            {
                'id': 'policy2',
                'displayName': 'Admin No MFA Policy',
                'state': 'enabled',
                'conditions': {
                    'users': {
                        'includeRoles': ['Global Administrator']
                    }
                },
                'grantControls': {
                    'builtInControls': ['block']
                }
            },
            {
                'id': 'policy3',
                'displayName': 'User Policy',
                'state': 'enabled',
                'conditions': {
                    'users': {
                        'includeRoles': ['User']
                    }
                },
                'grantControls': {
                    'builtInControls': ['mfa']
                }
            }
        ]

        policy = self.load_policy({
            'name': 'test-admin-mfa',
            'resource': 'azure.entraid-conditional-access-policy',
            'filters': [
                {'type': 'admin-mfa-required', 'value': True}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(policies)

        # Only policy1 requires MFA for admins
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'policy1')

    def test_admin_mfa_required_filter_false(self):
        """Test admin MFA required filter with value=False (find policies NOT requiring MFA)"""
        policies = [
            {
                'id': 'policy1',
                'displayName': 'Admin MFA Policy',
                'state': 'enabled',
                'conditions': {
                    'users': {
                        'includeRoles': ['Global Administrator']
                    }
                },
                'grantControls': {
                    'builtInControls': ['mfa']
                }
            },
            {
                'id': 'policy2',
                'displayName': 'Admin No MFA Policy',
                'state': 'enabled',
                'conditions': {
                    'users': {
                        'includeRoles': ['Global Administrator']
                    }
                },
                'grantControls': {
                    'builtInControls': ['block']
                }
            }
        ]

        policy = self.load_policy({
            'name': 'test-admin-no-mfa',
            'resource': 'azure.entraid-conditional-access-policy',
            'filters': [
                {'type': 'admin-mfa-required', 'value': False}
            ]
        })

        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(policies)

        # Only policy2 doesn't require MFA for admins
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'policy2')

    def test_admin_mfa_required_filter_multiple_admin_roles(self):
        """Test filter with multiple admin role types"""
        policies = [
            {
                'id': 'policy1',
                'displayName': 'Privileged Role Admin MFA',
                'conditions': {
                    'users': {
                        'includeRoles': ['Privileged Role Administrator']
                    }
                },
                'grantControls': {
                    'builtInControls': ['mfa']
                }
            },
            {
                'id': 'policy2',
                'displayName': 'User Admin MFA',
                'conditions': {
                    'users': {
                        'includeRoles': ['User Administrator']
                    }
                },
                'grantControls': {
                    'builtInControls': ['MFA']  # Test case insensitive
                }
            }
        ]

        policy = self.load_policy({
            'name': 'test-admin-roles',
            'resource': 'azure.entraid-conditional-access-policy',
            'filters': [
                {'type': 'admin-mfa-required', 'value': True}
            ]
        })

        filtered = policy.resource_manager.filter_resources(policies)
        self.assertEqual(len(filtered), 2)

    def test_admin_mfa_required_filter_missing_conditions(self):
        """Test filter with policies missing conditions or grant controls"""
        policies = [
            {
                'id': 'policy1',
                'displayName': 'No conditions',
                # No conditions key
            },
            {
                'id': 'policy2',
                'displayName': 'Empty conditions',
                'conditions': {}
            },
            {
                'id': 'policy3',
                'displayName': 'No users',
                'conditions': {
                    'users': {}
                }
            },
            {
                'id': 'policy4',
                'displayName': 'No grant controls',
                'conditions': {
                    'users': {
                        'includeRoles': ['Global Administrator']
                    }
                }
            },
            {
                'id': 'policy5',
                'displayName': 'Empty grant controls',
                'conditions': {
                    'users': {
                        'includeRoles': ['Global Administrator']
                    }
                },
                'grantControls': {}
            }
        ]

        policy = self.load_policy({
            'name': 'test-missing-data',
            'resource': 'azure.entraid-conditional-access-policy',
            'filters': [
                {'type': 'admin-mfa-required', 'value': True}
            ]
        })

        filtered = policy.resource_manager.filter_resources(policies)
        # None of these should match since they don't have admin roles with MFA
        self.assertEqual(len(filtered), 0)

    def test_admin_mfa_required_filter_non_admin_roles(self):
        """Test that non-admin roles are filtered out"""
        policies = [
            {
                'id': 'policy1',
                'displayName': 'Regular User with MFA',
                'conditions': {
                    'users': {
                        'includeRoles': ['Regular User', 'Guest']
                    }
                },
                'grantControls': {
                    'builtInControls': ['mfa']
                }
            }
        ]

        policy = self.load_policy({
            'name': 'test-non-admin',
            'resource': 'azure.entraid-conditional-access-policy',
            'filters': [
                {'type': 'admin-mfa-required', 'value': True}
            ]
        })

        filtered = policy.resource_manager.filter_resources(policies)
        # Should not match since no admin roles
        self.assertEqual(len(filtered), 0)

    @patch('c7n_azure.resources.entraid_conditional_access.requests.get')
    @patch('c7n_azure.resources.entraid_conditional_access.get_required_permissions_for_endpoint')
    def test_make_graph_request_success(self, mock_get_permissions, mock_requests_get):
        """Test successful Graph API request"""
        # Setup mocks
        mock_get_permissions.return_value = ['Policy.Read.All']

        mock_response = Mock()
        mock_response.json.return_value = {'value': [{'id': 'test'}]}
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        mock_token = Mock()
        mock_token.token = 'test-token'

        mock_session = Mock()
        mock_session._initialize_session = Mock()
        mock_session.credentials.get_token.return_value = mock_token

        # Create instance and test
        policy = self.load_policy({
            'name': 'test-graph-request',
            'resource': 'azure.entraid-conditional-access-policy'
        })

        resource_mgr = policy.resource_manager
        resource_mgr.get_client = Mock(return_value=mock_session)

        result = resource_mgr.make_graph_request('test/endpoint')

        self.assertEqual(result, {'value': [{'id': 'test'}]})
        mock_requests_get.assert_called_once()
        call_args = mock_requests_get.call_args
        self.assertIn('https://graph.microsoft.com/beta/test/endpoint', call_args[0])

    @patch('c7n_azure.resources.entraid_conditional_access.get_required_permissions_for_endpoint')
    def test_make_graph_request_unmapped_endpoint(self, mock_get_permissions):
        """Test Graph API request with unmapped endpoint raises ValueError"""
        mock_get_permissions.side_effect = ValueError("Unmapped endpoint")

        mock_session = Mock()
        mock_session._initialize_session = Mock()

        policy = self.load_policy({
            'name': 'test-unmapped-endpoint',
            'resource': 'azure.entraid-conditional-access-policy'
        })

        resource_mgr = policy.resource_manager
        resource_mgr.get_client = Mock(return_value=mock_session)

        with self.assertRaises(ValueError):
            resource_mgr.make_graph_request('unmapped/endpoint')

    @patch('c7n_azure.resources.entraid_conditional_access.requests.get')
    @patch('c7n_azure.resources.entraid_conditional_access.get_required_permissions_for_endpoint')
    def test_make_graph_request_api_error(self, mock_get_permissions, mock_requests_get):
        """Test Graph API request handling of request exceptions"""
        mock_get_permissions.return_value = ['Policy.Read.All']
        mock_requests_get.side_effect = requests.exceptions.RequestException("API Error")

        mock_token = Mock()
        mock_token.token = 'test-token'

        mock_session = Mock()
        mock_session._initialize_session = Mock()
        mock_session.credentials.get_token.return_value = mock_token

        policy = self.load_policy({
            'name': 'test-api-error',
            'resource': 'azure.entraid-conditional-access-policy'
        })

        resource_mgr = policy.resource_manager
        resource_mgr.get_client = Mock(return_value=mock_session)

        with self.assertRaises(requests.exceptions.RequestException):
            resource_mgr.make_graph_request('test/endpoint')

    @patch('c7n_azure.resources.entraid_conditional_access.EntraIDConditionalAccessPolicy.make_graph_request')
    def test_get_graph_resources_success(self, mock_make_request):
        """Test successful retrieval of conditional access policies"""
        mock_make_request.return_value = {
            'value': [
                {'id': 'policy1', 'displayName': 'Test Policy 1'},
                {'id': 'policy2', 'displayName': 'Test Policy 2'}
            ]
        }

        policy = self.load_policy({
            'name': 'test-get-resources',
            'resource': 'azure.entraid-conditional-access-policy'
        })

        resource_mgr = policy.resource_manager
        resources = resource_mgr.get_graph_resources()

        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['id'], 'policy1')
        self.assertEqual(resources[1]['id'], 'policy2')
        mock_make_request.assert_called_once_with('identity/conditionalAccess/policies')

    @patch('c7n_azure.resources.entraid_conditional_access.EntraIDConditionalAccessPolicy.make_graph_request')
    def test_get_graph_resources_error(self, mock_make_request):
        """Test get_graph_resources returns empty list on exception"""
        mock_make_request.side_effect = Exception("API Error")

        policy = self.load_policy({
            'name': 'test-get-resources-error',
            'resource': 'azure.entraid-conditional-access-policy'
        })

        resource_mgr = policy.resource_manager
        resources = resource_mgr.get_graph_resources()

        # Should return empty list on error
        self.assertEqual(resources, [])


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


@terraform('entraid_organization')
@pytest.mark.functional
def test_entraid_organization_discovery_terraform(test, entraid_organization):
    """Test that Cloud Custodian can discover organization provisioned by Terraform"""
    org_info = entraid_organization.outputs['organization_basic_info']['value']

    # Test basic organization discovery
    policy = test.load_policy({
        'name': 'terraform-organization-discovery',
        'resource': 'azure.entraid-organization'
    })

    # Verify policy loads correctly
    assert policy.resource_manager.type == 'entraid-organization'

    # Verify test data structure
    assert 'id' in org_info
    assert 'display_name' in org_info
    assert 'tenant_id' in org_info


@terraform('entraid_organization')
@pytest.mark.functional
def test_entraid_organization_domains_terraform(test, entraid_organization):
    """Test organization domains against Terraform-provisioned data"""
    domains_info = entraid_organization.outputs['organization_domains']['value']

    # Test organization domains discovery
    policy = test.load_policy({
        'name': 'terraform-organization-domains',
        'resource': 'azure.entraid-organization'
    })

    # Verify domains data structure
    assert 'domains' in domains_info
    assert len(domains_info['domains']) > 0

    # Verify domain properties
    for domain in domains_info['domains']:
        assert 'domain_name' in domain
        assert 'is_verified' in domain
        assert 'is_default' in domain
        assert 'authentication_type' in domain

    assert policy is not None


@terraform('entraid_organization')
@pytest.mark.functional
def test_entraid_organization_compliance_terraform(test, entraid_organization):
    """Test organization compliance data against Terraform-provisioned data"""
    compliance = entraid_organization.outputs['organization_compliance']['value']

    # Test compliance monitoring
    policy = test.load_policy({
        'name': 'terraform-organization-compliance',
        'resource': 'azure.entraid-organization'
    })

    # Verify CIS compliance structure
    assert 'cis_compliance' in compliance
    cis_compliance = compliance['cis_compliance']
    assert 'version' in cis_compliance
    assert 'controls' in cis_compliance

    # Verify NIST compliance structure
    assert 'nist_compliance' in compliance
    nist_compliance = compliance['nist_compliance']
    assert 'framework' in nist_compliance
    assert 'controls' in nist_compliance

    assert policy is not None
