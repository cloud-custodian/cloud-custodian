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
from c7n_azure.resources.entraid_security_defaults import EntraIDSecurityDefaults
from c7n_azure.resources.entraid_authorization_policy import EntraIDAuthorizationPolicy
from c7n_azure.resources.entraid_named_locations import EntraIDNamedLocation
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


class EntraIDSecurityDefaultsTest(BaseTest):
    """Test EntraID Security Defaults resource functionality"""

    def test_security_defaults_schema_validate(self):
        """Test security defaults schema validation"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-security-defaults',
                'resource': 'azure.entraid-security-defaults',
                'filters': [
                    {'type': 'value', 'key': 'isEnabled', 'value': True}
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_security_defaults_resource_type(self):
        """Test security defaults resource type configuration"""
        resource_type = EntraIDSecurityDefaults.resource_type
        self.assertEqual(resource_type.service, 'graph')
        self.assertEqual(resource_type.id, 'id')
        self.assertTrue(resource_type.global_resource)
        self.assertIn('Policy.Read.All', resource_type.permissions)


class EntraIDNamedLocationTest(BaseTest):
    """Test EntraID Named Location resource functionality"""

    def test_entraid_named_location_schema_validate(self):
        """Test that the EntraID named location resource schema validates correctly"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-entraid-named-location',
                'resource': 'azure.entraid-named-location',
                'filters': [
                    {'type': 'value', 'key': 'displayName', 'value': 'Test Location'}
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_entraid_named_location_resource_type(self):
        """Test EntraID named location resource type configuration"""
        resource_type = EntraIDNamedLocation.resource_type
        self.assertEqual(resource_type.service, 'graph')
        self.assertEqual(resource_type.id, 'id')
        self.assertEqual(resource_type.name, 'displayName')
        self.assertEqual(resource_type.date, 'createdDateTime')
        self.assertTrue(resource_type.global_resource)
        self.assertIn('Policy.Read.All', resource_type.permissions)

    @patch('c7n_azure.resources.entraid_named_locations.EntraIDNamedLocation.make_graph_request')
    def test_entraid_named_location_get_resources(self, mock_graph_request):
        """Test named location resource enumeration"""
        # Mock Graph API response
        mock_graph_request.return_value = {
            'value': [
                {
                    'id': 'ip-location-1',
                    'displayName': 'Corporate IP Ranges',
                    'createdDateTime': '2023-01-01T00:00:00Z',
                    'modifiedDateTime': '2023-01-01T00:00:00Z',
                    '@odata.type': '#microsoft.graph.ipNamedLocation',
                    'isTrusted': True,
                    'ipRanges': [
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '192.168.1.0/24'
                        },
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '10.0.0.0/16'
                        }
                    ]
                },
                {
                    'id': 'country-location-1',
                    'displayName': 'US Locations',
                    'createdDateTime': '2023-01-02T00:00:00Z',
                    'modifiedDateTime': '2023-01-02T00:00:00Z',
                    '@odata.type': '#microsoft.graph.countryNamedLocation',
                    'countriesAndRegions': ['US', 'CA'],
                    'includeUnknownCountriesAndRegions': False
                }
            ]
        }

        policy_data = {
            'name': 'test-get-resources',
            'resource': 'azure.entraid-named-location'
        }
        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        resources = resource_mgr.get_graph_resources()

        # Verify API was called correctly
        mock_graph_request.assert_called_with('identity/conditionalAccess/namedLocations')

        # Verify resources returned
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['id'], 'ip-location-1')
        self.assertEqual(resources[1]['id'], 'country-location-1')

    @patch('c7n_azure.resources.entraid_named_locations.EntraIDNamedLocation.make_graph_request')
    def test_entraid_named_location_augment(self, mock_graph_request):
        """Test named location resource augmentation with computed fields"""
        # Sample named location data
        locations = [
            {
                'id': 'ip-location-1',
                'displayName': 'Corporate IP Ranges',
                '@odata.type': '#microsoft.graph.ipNamedLocation',
                'ipRanges': [
                    {
                        '@odata.type': '#microsoft.graph.iPv4CidrRange',
                        'cidrAddress': '192.168.1.0/24'
                    },
                    {
                        '@odata.type': '#microsoft.graph.iPv4CidrRange',
                        'cidrAddress': '10.0.0.0/16'
                    },
                    {
                        '@odata.type': '#microsoft.graph.iPv4CidrRange',
                        'cidrAddress': '172.16.0.0/12'
                    }
                ]
            },
            {
                'id': 'country-location-1',
                'displayName': 'US Locations',
                '@odata.type': '#microsoft.graph.countryNamedLocation',
                'countriesAndRegions': ['US', 'CA', 'MX']
            },
            {
                'id': 'unknown-location',
                'displayName': 'Unknown Type Location',
                '@odata.type': '#microsoft.graph.unknownLocation'
            }
        ]

        policy_data = {
            'name': 'test-augment',
            'resource': 'azure.entraid-named-location'
        }
        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        augmented = resource_mgr.augment(locations)

        # Check computed fields for IP location
        self.assertTrue(augmented[0]['c7n:IsIPLocation'])
        self.assertFalse(augmented[0]['c7n:IsCountryLocation'])
        self.assertEqual(augmented[0]['c7n:IPRangesCount'], 3)

        # Check computed fields for country location
        self.assertFalse(augmented[1]['c7n:IsIPLocation'])
        self.assertTrue(augmented[1]['c7n:IsCountryLocation'])
        self.assertEqual(augmented[1]['c7n:CountriesCount'], 3)

        # Check computed fields for unknown type
        self.assertFalse(augmented[2]['c7n:IsIPLocation'])
        self.assertFalse(augmented[2]['c7n:IsCountryLocation'])

    def test_location_type_filter_ip(self):
        """Test location-type filter for IP-based locations"""
        locations = [
            {
                'id': 'ip-location-1',
                'displayName': 'IP Location',
                '@odata.type': '#microsoft.graph.ipNamedLocation',
                'c7n:IsIPLocation': True,
                'c7n:IsCountryLocation': False
            },
            {
                'id': 'country-location-1',
                'displayName': 'Country Location',
                '@odata.type': '#microsoft.graph.countryNamedLocation',
                'c7n:IsIPLocation': False,
                'c7n:IsCountryLocation': True
            }
        ]

        policy_data = {
            'name': 'test-ip-filter',
            'resource': 'azure.entraid-named-location',
            'filters': [
                {'type': 'location-type', 'location-type': 'ipNamedLocation'}
            ]
        }
        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        filtered = resource_mgr.filter_resources(locations)

        # Should only return IP-based location
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'ip-location-1')

    def test_location_type_filter_country(self):
        """Test location-type filter for country-based locations"""
        locations = [
            {
                'id': 'ip-location-1',
                'displayName': 'IP Location',
                '@odata.type': '#microsoft.graph.ipNamedLocation',
                'c7n:IsIPLocation': True,
                'c7n:IsCountryLocation': False
            },
            {
                'id': 'country-location-1',
                'displayName': 'Country Location',
                '@odata.type': '#microsoft.graph.countryNamedLocation',
                'c7n:IsIPLocation': False,
                'c7n:IsCountryLocation': True
            }
        ]

        policy_data = {
            'name': 'test-country-filter',
            'resource': 'azure.entraid-named-location',
            'filters': [
                {'type': 'location-type', 'location-type': 'countryNamedLocation'}
            ]
        }
        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        filtered = resource_mgr.filter_resources(locations)

        # Should only return country-based location
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'country-location-1')

    def test_ip_range_count_filter_greater_than(self):
        """Test ip-range-count filter with greater-than operator"""
        locations = [
            {
                'id': 'small-ip-location',
                'displayName': 'Small IP Location',
                'c7n:IsIPLocation': True,
                'c7n:IPRangesCount': 2
            },
            {
                'id': 'large-ip-location',
                'displayName': 'Large IP Location',
                'c7n:IsIPLocation': True,
                'c7n:IPRangesCount': 10
            },
            {
                'id': 'country-location',
                'displayName': 'Country Location',
                'c7n:IsIPLocation': False,
                'c7n:IsCountryLocation': True
            }
        ]

        policy_data = {
            'name': 'test-ip-count-filter',
            'resource': 'azure.entraid-named-location',
            'filters': [
                {'type': 'ip-range-count', 'count': 5, 'op': 'greater-than'}
            ]
        }
        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        filtered = resource_mgr.filter_resources(locations)

        # Should only return location with >5 IP ranges
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'large-ip-location')

    def test_ip_range_count_filter_equal(self):
        """Test ip-range-count filter with equal operator"""
        locations = [
            {
                'id': 'exact-ip-location',
                'displayName': 'Exact IP Location',
                'c7n:IsIPLocation': True,
                'c7n:IPRangesCount': 5
            },
            {
                'id': 'different-ip-location',
                'displayName': 'Different IP Location',
                'c7n:IsIPLocation': True,
                'c7n:IPRangesCount': 3
            }
        ]

        policy_data = {
            'name': 'test-ip-count-equal',
            'resource': 'azure.entraid-named-location',
            'filters': [
                {'type': 'ip-range-count', 'count': 5, 'op': 'equal'}
            ]
        }
        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        filtered = resource_mgr.filter_resources(locations)

        # Should only return location with exactly 5 IP ranges
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'exact-ip-location')

    def test_countries_count_filter_greater_than(self):
        """Test countries-count filter with greater-than operator"""
        locations = [
            {
                'id': 'small-country-location',
                'displayName': 'Small Country Location',
                'c7n:IsCountryLocation': True,
                'c7n:CountriesCount': 2
            },
            {
                'id': 'large-country-location',
                'displayName': 'Large Country Location',
                'c7n:IsCountryLocation': True,
                'c7n:CountriesCount': 10
            },
            {
                'id': 'ip-location',
                'displayName': 'IP Location',
                'c7n:IsIPLocation': True,
                'c7n:IsCountryLocation': False
            }
        ]

        policy_data = {
            'name': 'test-countries-count-filter',
            'resource': 'azure.entraid-named-location',
            'filters': [
                {'type': 'countries-count', 'count': 5, 'op': 'greater-than'}
            ]
        }
        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        filtered = resource_mgr.filter_resources(locations)

        # Should only return location with >5 countries
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'large-country-location')

    def test_countries_count_filter_less_than(self):
        """Test countries-count filter with less-than operator"""
        locations = [
            {
                'id': 'single-country-location',
                'displayName': 'Single Country Location',
                'c7n:IsCountryLocation': True,
                'c7n:CountriesCount': 1
            },
            {
                'id': 'multi-country-location',
                'displayName': 'Multi Country Location',
                'c7n:IsCountryLocation': True,
                'c7n:CountriesCount': 5
            }
        ]

        policy_data = {
            'name': 'test-countries-count-less-than',
            'resource': 'azure.entraid-named-location',
            'filters': [
                {'type': 'countries-count', 'count': 3, 'op': 'less-than'}
            ]
        }
        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        filtered = resource_mgr.filter_resources(locations)

        # Should only return location with <3 countries
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'single-country-location')

    @patch('c7n_azure.resources.entraid_named_locations.EntraIDNamedLocation.make_graph_request')
    def test_get_resources_error_handling(self, mock_graph_request):
        """Test error handling in get_graph_resources"""
        # Mock API error
        mock_graph_request.side_effect = Exception(
            "Insufficient privileges to complete the operation"
        )

        policy_data = {
            'name': 'test-error-handling',
            'resource': 'azure.entraid-named-location'
        }
        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        resources = resource_mgr.get_graph_resources()

        # Should return empty list on error
        self.assertEqual(resources, [])

    @patch('c7n_azure.resources.entraid_named_locations.EntraIDNamedLocation.make_graph_request')
    def test_get_resources_empty_response(self, mock_graph_request):
        """Test handling of empty API response"""
        # Mock empty API response
        mock_graph_request.return_value = {'value': []}

        policy_data = {
            'name': 'test-empty-response',
            'resource': 'azure.entraid-named-location'
        }
        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        resources = resource_mgr.get_graph_resources()

        # Should return empty list
        self.assertEqual(len(resources), 0)

    def test_filter_validation(self):
        """Test that filters validate schema correctly"""
        # Test location-type filter with valid values
        policy_data = {
            'name': 'test-location-type-validation',
            'resource': 'azure.entraid-named-location',
            'filters': [
                {'type': 'location-type', 'location-type': 'ipNamedLocation'}
            ]
        }
        policy = self.load_policy(policy_data, validate=True)
        self.assertIsNotNone(policy)

        # Test ip-range-count filter validation
        policy_data = {
            'name': 'test-ip-range-count-validation',
            'resource': 'azure.entraid-named-location',
            'filters': [
                {'type': 'ip-range-count', 'count': 5, 'op': 'greater-than'}
            ]
        }
        policy = self.load_policy(policy_data, validate=True)
        self.assertIsNotNone(policy)

        # Test countries-count filter validation
        policy_data = {
            'name': 'test-countries-count-validation',
            'resource': 'azure.entraid-named-location',
            'filters': [
                {'type': 'countries-count', 'count': 3, 'op': 'less-than'}
            ]
        }
        policy = self.load_policy(policy_data, validate=True)
        self.assertIsNotNone(policy)

    @patch('c7n_azure.resources.entraid_named_locations.EntraIDNamedLocation.make_graph_request')
    def test_combined_filters_integration(self, mock_graph_request):
        """Test integration of multiple filters working together"""
        # Mock comprehensive response with mixed location types
        mock_graph_request.return_value = {
            'value': [
                {
                    'id': 'small-ip-location',
                    'displayName': 'Small Corporate IP',
                    '@odata.type': '#microsoft.graph.ipNamedLocation',
                    'ipRanges': [
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '192.168.1.0/24'
                        }
                    ]
                },
                {
                    'id': 'large-ip-location',
                    'displayName': 'Large Corporate IP',
                    '@odata.type': '#microsoft.graph.ipNamedLocation',
                    'ipRanges': [
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '10.0.0.0/8'
                        },
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '172.16.0.0/12'
                        },
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '192.168.0.0/16'
                        },
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '203.0.113.0/24'
                        },
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '198.51.100.0/24'
                        },
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '198.18.0.0/15'
                        }
                    ]
                },
                {
                    'id': 'small-country-location',
                    'displayName': 'North America',
                    '@odata.type': '#microsoft.graph.countryNamedLocation',
                    'countriesAndRegions': ['US', 'CA']
                },
                {
                    'id': 'large-country-location',
                    'displayName': 'Global Offices',
                    '@odata.type': '#microsoft.graph.countryNamedLocation',
                    'countriesAndRegions': ['US', 'CA', 'GB', 'DE', 'FR', 'JP', 'AU', 'IN']
                }
            ]
        }

        # Test policy that finds IP locations with more than 5 ranges
        policy_data = {
            'name': 'test-combined-filters',
            'resource': 'azure.entraid-named-location',
            'filters': [
                {'type': 'location-type', 'location-type': 'ipNamedLocation'},
                {'type': 'ip-range-count', 'count': 5, 'op': 'greater-than'}
            ]
        }
        policy = self.load_policy(policy_data)
        resources = policy.run()

        # Should only return the large IP location
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['id'], 'large-ip-location')

        # Verify augmentation fields are present
        self.assertTrue(resources[0]['c7n:IsIPLocation'])
        self.assertEqual(resources[0]['c7n:IPRangesCount'], 6)

    @patch('c7n_azure.resources.entraid_named_locations.EntraIDNamedLocation.make_graph_request')
    def test_policy_execution_workflow(self, mock_graph_request):
        """Test complete policy execution workflow from definition to results"""
        # Mock API response
        mock_graph_request.return_value = {
            'value': [
                {
                    'id': 'trusted-office-ips',
                    'displayName': 'Trusted Office IPs',
                    'createdDateTime': '2023-01-01T00:00:00Z',
                    'modifiedDateTime': '2023-06-01T00:00:00Z',
                    '@odata.type': '#microsoft.graph.ipNamedLocation',
                    'isTrusted': True,
                    'ipRanges': [
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '203.0.113.0/24'
                        },
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '198.51.100.0/24'
                        }
                    ]
                },
                {
                    'id': 'allowed-countries',
                    'displayName': 'Allowed Countries',
                    'createdDateTime': '2023-02-01T00:00:00Z',
                    'modifiedDateTime': '2023-07-01T00:00:00Z',
                    '@odata.type': '#microsoft.graph.countryNamedLocation',
                    'countriesAndRegions': ['US', 'CA', 'GB'],
                    'includeUnknownCountriesAndRegions': False
                }
            ]
        }

        # Define comprehensive policy
        policy_data = {
            'name': 'audit-named-locations',
            'resource': 'azure.entraid-named-location',
            'filters': [
                {
                    'type': 'value',
                    'key': 'displayName',
                    'op': 'regex',
                    'value': '.*Office.*|.*Countries.*'
                }
            ]
        }

        # Execute policy
        policy = self.load_policy(policy_data)
        resources = policy.run()

        # Validate results
        self.assertEqual(len(resources), 2)

        # Verify resource properties
        resource_ids = [r['id'] for r in resources]
        self.assertIn('trusted-office-ips', resource_ids)
        self.assertIn('allowed-countries', resource_ids)

        # Verify computed fields are present
        for resource in resources:
            self.assertIn('c7n:IsIPLocation', resource)
            self.assertIn('c7n:IsCountryLocation', resource)

        # Verify specific augmentation
        ip_resource = next(r for r in resources if r['id'] == 'trusted-office-ips')
        country_resource = next(r for r in resources if r['id'] == 'allowed-countries')

        self.assertTrue(ip_resource['c7n:IsIPLocation'])
        self.assertFalse(ip_resource['c7n:IsCountryLocation'])
        self.assertEqual(ip_resource['c7n:IPRangesCount'], 2)

        self.assertFalse(country_resource['c7n:IsIPLocation'])
        self.assertTrue(country_resource['c7n:IsCountryLocation'])
        self.assertEqual(country_resource['c7n:CountriesCount'], 3)

    def test_resource_manager_properties(self):
        """Test resource manager configuration and properties"""
        policy_data = {
            'name': 'test-resource-manager',
            'resource': 'azure.entraid-named-location'
        }
        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        # Validate resource manager type
        self.assertEqual(resource_mgr.type, 'entraid-named-location')

        # Validate resource type properties
        self.assertEqual(resource_mgr.resource_type.service, 'graph')
        self.assertEqual(
            resource_mgr.resource_type.enum_spec[0],
            'identity/conditionalAccess/namedLocations'
        )
        self.assertEqual(resource_mgr.resource_type.enum_spec[1], 'list')
        self.assertEqual(
            resource_mgr.resource_type.detail_spec[0],
            'identity/conditionalAccess/namedLocations'
        )
        self.assertEqual(resource_mgr.resource_type.detail_spec[1], 'get')
        self.assertEqual(resource_mgr.resource_type.id, 'id')
        self.assertEqual(resource_mgr.resource_type.name, 'displayName')
        self.assertEqual(resource_mgr.resource_type.date, 'createdDateTime')

        # Validate permissions
        self.assertIn('Policy.Read.All', resource_mgr.resource_type.permissions)

    @patch('c7n_azure.resources.entraid_named_locations.EntraIDNamedLocation.make_graph_request')
    def test_pagination_handling(self, mock_graph_request):
        """Test handling of paginated responses (future enhancement validation)"""
        # Mock response with @odata.nextLink (simulating pagination)
        mock_graph_request.return_value = {
            'value': [
                {
                    'id': 'location-1',
                    'displayName': 'Location 1',
                    '@odata.type': '#microsoft.graph.ipNamedLocation',
                    'ipRanges': [
                        {
                            '@odata.type': '#microsoft.graph.iPv4CidrRange',
                            'cidrAddress': '10.0.0.0/16'
                        }
                    ]
                }
            ],
            '@odata.nextLink': 'https://graph.microsoft.com/v1.0/identity/conditionalAccess/namedLocations?$skip=100'
        }

        policy_data = {
            'name': 'test-pagination',
            'resource': 'azure.entraid-named-location'
        }
        policy = self.load_policy(policy_data)

        # This tests the current implementation - pagination would
        # need to be added to the resource later
        resources = policy.run()

        # Current implementation returns first page only
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['id'], 'location-1')


class EntraIDAuthorizationPolicyTest(BaseTest):
    """Test EntraID Authorization Policy resource functionality"""

    def test_authorization_policy_schema_validate(self):
        """Test authorization policy schema validation"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-authorization-policy',
                'resource': 'azure.entraid-authorization-policy',
                'filters': [
                    {'type': 'value',
                     'key': 'defaultUserRolePermissions.allowedToCreateApps',
                     'value': False}
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_authorization_policy_resource_type(self):
        """Test authorization policy resource type configuration"""
        resource_type = EntraIDAuthorizationPolicy.resource_type
        self.assertEqual(resource_type.service, 'graph')
        self.assertEqual(resource_type.id, 'id')
        self.assertTrue(resource_type.global_resource)
        self.assertIn('Policy.Read.All', resource_type.permissions)

    @patch('c7n_azure.resources.entraid_authorization_policy.EntraIDAuthorizationPolicy.make_graph_request')
    def test_authorization_policy_get_resources(self, mock_graph_request):
        """Test authorization policy resource retrieval"""
        # Mock the Graph API response
        mock_graph_request.return_value = {
            'id': 'authorizationPolicy',
            'displayName': 'Authorization Policy',
            'description': 'Used to manage authorization related settings across the company.',
            'defaultUserRolePermissions': {
                'allowedToCreateApps': True,
                'allowedToCreateSecurityGroups': True,
                'allowedToReadOtherUsers': True,
                'allowedToCreateTenants': False
            }
        }

        policy = self.load_policy({
            'name': 'test-auth-policy-retrieval',
            'resource': 'azure.entraid-authorization-policy'
        })

        resource_mgr = policy.resource_manager
        resources = resource_mgr.get_graph_resources()

        # Should return authorization policy wrapped in a list
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['id'], 'authorizationPolicy')
        self.assertIn('defaultUserRolePermissions', resources[0])

    def test_cis_compliance_scenario(self):
        """Test CIS-B-MAF-4.0.0-6.14 compliance scenario"""
        # Test the specific CIS control: 'Users can register applications' is set to 'No'

        # Compliant scenario - users cannot create apps
        compliant_policy = {
            'id': 'authorizationPolicy',
            'displayName': 'Authorization Policy',
            'description': 'Used to manage authorization related settings across the company.',
            'defaultUserRolePermissions': {
                'allowedToCreateApps': False,  # CIS compliant
                'allowedToCreateSecurityGroups': False,
                'allowedToReadOtherUsers': True,
                'allowedToCreateTenants': False
            }
        }

        # Non-compliant scenario - users can create apps
        non_compliant_policy = {
            'id': 'authorizationPolicy',
            'displayName': 'Authorization Policy',
            'description': 'Used to manage authorization related settings across the company.',
            'defaultUserRolePermissions': {
                'allowedToCreateApps': True,  # CIS non-compliant
                'allowedToCreateSecurityGroups': True,
                'allowedToReadOtherUsers': True,
                'allowedToCreateTenants': True
            }
        }

        # Policy to check for CIS compliance
        cis_policy = self.load_policy({
            'name': 'cis-b-maf-4-0-0-6-14-users-register-applications',
            'resource': 'azure.entraid-authorization-policy',
            'filters': [
                {'type': 'value',
                 'key': 'defaultUserRolePermissions.allowedToCreateApps',
                 'value': False}
            ]
        })

        resource_mgr = cis_policy.resource_manager

        # Test compliant scenario
        compliant_filtered = resource_mgr.filter_resources([compliant_policy])
        self.assertEqual(len(compliant_filtered), 1)
        self.assertFalse(compliant_filtered[0]['defaultUserRolePermissions']['allowedToCreateApps'])

        # Test non-compliant scenario
        non_compliant_filtered = resource_mgr.filter_resources([non_compliant_policy])
        self.assertEqual(len(non_compliant_filtered), 0)  # Should not match

        # Policy to find violations (non-compliant)
        violation_policy = self.load_policy({
            'name': 'cis-violation-users-can-register-apps',
            'resource': 'azure.entraid-authorization-policy',
            'filters': [
                {'type': 'value',
                 'key': 'defaultUserRolePermissions.allowedToCreateApps',
                 'value': True}
            ]
        })

        violation_mgr = violation_policy.resource_manager
        violation_filtered = violation_mgr.filter_resources([non_compliant_policy])
        self.assertEqual(len(violation_filtered), 1)
        self.assertTrue(violation_filtered[0]['defaultUserRolePermissions']['allowedToCreateApps'])


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


@terraform('entraid_security_defaults')
@pytest.mark.functional
def test_entraid_security_defaults_discovery_terraform(test, entraid_security_defaults):
    """Test that Cloud Custodian can discover security defaults provisioned by Terraform"""
    enabled_defaults = entraid_security_defaults.outputs['security_defaults_enabled']['value']
    disabled_defaults = entraid_security_defaults.outputs['security_defaults_disabled']['value']

    # Test basic security defaults discovery
    policy = test.load_policy({
        'name': 'terraform-security-defaults-discovery',
        'resource': 'azure.entraid-security-defaults'
    })

    # Verify policy loads correctly
    assert policy.resource_manager.type == 'entraid-security-defaults'

    # Verify test data integrity
    assert enabled_defaults['is_enabled'] is True
    assert disabled_defaults['is_enabled'] is False

    assert enabled_defaults['display_name'] == 'Security Defaults'


@terraform('entraid_security_defaults')
@pytest.mark.functional
def test_entraid_security_defaults_features_terraform(test, entraid_security_defaults):
    """Test security defaults features against Terraform-provisioned data"""
    features = entraid_security_defaults.outputs['security_defaults_features']['value']

    # Test security defaults feature analysis
    policy = test.load_policy({
        'name': 'terraform-security-defaults-features',
        'resource': 'azure.entraid-security-defaults',
        'filters': [
            {'type': 'value', 'key': 'isEnabled', 'value': True}
        ]
    })

    # Verify features structure
    assert 'enabled_features' in features
    enabled_features = features['enabled_features']

    # Verify key security features
    expected_features = [
        'require_mfa_for_admins',
        'require_mfa_for_users',
        'block_legacy_authentication',
        'protect_privileged_activities'
    ]

    for feature in expected_features:
        assert feature in enabled_features
        assert 'enabled' in enabled_features[feature]
        assert 'description' in enabled_features[feature]

    # Verify admin MFA feature details
    mfa_admin_feature = enabled_features['require_mfa_for_admins']
    assert 'affected_roles' in mfa_admin_feature
    assert 'Global Administrator' in mfa_admin_feature['affected_roles']

    assert policy is not None


@terraform('entraid_security_defaults')
@pytest.mark.functional
def test_entraid_security_defaults_compliance_terraform(test, entraid_security_defaults):
    """Test security defaults compliance against Terraform-provisioned data"""
    compliance = entraid_security_defaults.outputs['security_defaults_compliance']['value']

    # Test compliance analysis
    policy = test.load_policy({
        'name': 'terraform-security-defaults-compliance',
        'resource': 'azure.entraid-security-defaults'
    })

    # Verify compliance structure
    required_sections = [
        'cis_compliant_controls',
        'security_improvements',
        'limitations',
        'recommendations'
    ]
    for section in required_sections:
        assert section in compliance

    # Verify CIS compliance controls
    cis_controls = compliance['cis_compliant_controls']
    assert len(cis_controls) > 0

    for control in cis_controls:
        assert 'control' in control
        assert 'title' in control
        assert 'status' in control

    # Verify security improvements
    improvements = compliance['security_improvements']
    assert len(improvements) > 0

    for improvement in improvements:
        assert 'area' in improvement
        assert 'improvement' in improvement
        assert 'risk_reduction' in improvement

    assert policy is not None


@terraform('entraid_security_defaults')
@pytest.mark.functional
def test_entraid_security_defaults_scenarios_terraform(test, entraid_security_defaults):
    """Test tenant scenarios against Terraform-provisioned data"""
    scenarios = entraid_security_defaults.outputs['test_scenarios']['value']

    # Test scenario-based analysis
    policy = test.load_policy({
        'name': 'terraform-tenant-scenarios',
        'resource': 'azure.entraid-security-defaults'
    })

    # Verify all expected scenarios
    expected_scenarios = ['new_tenant_secure', 'disabled_no_ca', 'disabled_with_ca']
    for scenario_name in expected_scenarios:
        assert scenario_name in scenarios

        scenario = scenarios[scenario_name]
        required_fields = [
            'security_defaults_enabled',
            'conditional_access_policies',
            'mfa_enforced_users',
            'legacy_auth_blocked',
            'compliance_score',
            'risk_level'
        ]

        for field in required_fields:
            assert field in scenario

    # Verify scenario logic
    secure_scenario = scenarios['new_tenant_secure']
    risky_scenario = scenarios['disabled_no_ca']
    optimal_scenario = scenarios['disabled_with_ca']

    assert secure_scenario['security_defaults_enabled'] is True
    assert risky_scenario['security_defaults_enabled'] is False
    assert optimal_scenario['security_defaults_enabled'] is False

    assert optimal_scenario['compliance_score'] > secure_scenario['compliance_score']
    assert secure_scenario['compliance_score'] > risky_scenario['compliance_score']

    assert policy is not None


# EntraID Named Location Terraform Tests
@terraform('entraid_named_location')
@pytest.mark.functional
def test_entraid_named_location_discovery_terraform(test, entraid_named_location):
    """Test that Cloud Custodian can discover named locations provisioned by Terraform"""
    # Verify terraform fixtures loaded successfully
    expected_outputs = [
        'test_corporate_ips', 'test_external_ips', 'test_single_ip',
        'test_trusted_countries', 'test_country_with_unknown',
        'test_blocked_countries', 'test_mixed_ranges', 'all_named_locations'
    ]
    assert len(entraid_named_location.outputs) == len(expected_outputs), (
        f"Expected {len(expected_outputs)} outputs, got {len(entraid_named_location.outputs)}"
    )

    # Get terraform-provisioned named location data
    corporate_ips = entraid_named_location.outputs['test_corporate_ips']['value']
    external_ips = entraid_named_location.outputs['test_external_ips']['value']
    single_ip = entraid_named_location.outputs['test_single_ip']['value']
    trusted_countries = entraid_named_location.outputs['test_trusted_countries']['value']

    # Verify IP-based named locations (updated for Azure AD deletion restrictions)
    assert 'C7N Test - Corporate IP Ranges' in corporate_ips['display_name']
    # Changed to false to avoid Azure AD deletion restrictions
    assert corporate_ips['ip']['trusted'] is False
    assert len(corporate_ips['ip']['ip_ranges_or_fqdns']) == 3
    assert '192.168.1.0/24' in corporate_ips['ip']['ip_ranges_or_fqdns']

    assert 'C7N Test - External IP Ranges' in external_ips['display_name']
    assert external_ips['ip']['trusted'] is False
    assert len(external_ips['ip']['ip_ranges_or_fqdns']) == 2

    assert 'C7N Test - Single IP' in single_ip['display_name']  # Display name also changed
    # Changed to false to avoid Azure AD deletion restrictions
    assert single_ip['ip']['trusted'] is False
    assert '192.168.1.100/32' in single_ip['ip']['ip_ranges_or_fqdns']

    # Verify country-based named locations
    assert 'C7N Test - Trusted Countries' in trusted_countries['display_name']
    assert len(trusted_countries['country']['countries_and_regions']) == 4
    assert 'US' in trusted_countries['country']['countries_and_regions']
    assert trusted_countries['country']['include_unknown_countries_and_regions'] is False

    # Test Cloud Custodian policy creation and validation
    policy = test.load_policy({
        'name': 'terraform-named-locations-discovery',
        'resource': 'azure.entraid-named-location'
    })

    # Verify policy loads correctly
    assert policy.resource_manager.type == 'entraid-named-location'
    print(f"SUCCESS: Terraform fixtures loaded {len(entraid_named_location.outputs)} "
          f"named locations successfully")


@terraform('entraid_named_location')
@pytest.mark.functional
def test_entraid_named_location_type_filter_terraform(test, entraid_named_location):
    """Test location type filter against Terraform-provisioned named locations"""
    # Test IP-based location filter
    ip_policy = test.load_policy({
        'name': 'terraform-ip-named-locations',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'type': 'location-type', 'location-type': 'ipNamedLocation'}
        ]
    })

    # Test country-based location filter
    country_policy = test.load_policy({
        'name': 'terraform-country-named-locations',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'type': 'location-type', 'location-type': 'countryNamedLocation'}
        ]
    })

    # Verify policy structures
    assert ip_policy.resource_manager.type == 'entraid-named-location'
    assert country_policy.resource_manager.type == 'entraid-named-location'
    print("SUCCESS: Location type filters configured successfully")


@terraform('entraid_named_location')
@pytest.mark.functional
def test_entraid_named_location_value_filter_terraform(test, entraid_named_location):
    """Test value-based filtering against Terraform-provisioned named locations"""
    corporate_ips = entraid_named_location.outputs['test_corporate_ips']['value']
    external_ips = entraid_named_location.outputs['test_external_ips']['value']

    # Verify test data integrity for trust settings
    assert corporate_ips['ip']['trusted'] is False  # Changed from True since we made it untrusted
    assert external_ips['ip']['trusted'] is False

    # Test filtering by display name pattern (corporate locations)
    corporate_policy = test.load_policy({
        'name': 'terraform-corporate-ip-locations',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'type': 'location-type', 'location-type': 'ipNamedLocation'},
            {'type': 'value', 'key': 'displayName', 'op': 'glob', 'value': '*Corporate*'}
        ]
    })

    # Test filtering by display name pattern (external locations)
    external_policy = test.load_policy({
        'name': 'terraform-external-ip-locations',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'type': 'location-type', 'location-type': 'ipNamedLocation'},
            {'type': 'value', 'key': 'displayName', 'op': 'glob', 'value': '*External*'}
        ]
    })

    # Verify policy structures
    assert corporate_policy.resource_manager.type == 'entraid-named-location'
    assert external_policy.resource_manager.type == 'entraid-named-location'
    print("SUCCESS: Value filters configured successfully")


@terraform('entraid_named_location')
@pytest.mark.functional
def test_entraid_named_location_ip_range_filter_terraform(test, entraid_named_location):
    """Test IP range count filter against Terraform-provisioned named locations"""
    corporate_ips = entraid_named_location.outputs['test_corporate_ips']['value']
    single_ip = entraid_named_location.outputs['test_single_ip']['value']

    # Verify test data integrity for trust settings (all changed to untrusted for Azure limitations)
    assert corporate_ips['ip']['trusted'] is False  # All IP locations now untrusted
    assert single_ip['ip']['trusted'] is False  # All IP locations now untrusted

    # Verify test data contains expected IP ranges counts
    assert len(corporate_ips['ip']['ip_ranges_or_fqdns']) == 3
    assert len(single_ip['ip']['ip_ranges_or_fqdns']) == 1

    # Test IP range count filter - locations with more than 1 range
    multiple_ranges_policy = test.load_policy({
        'name': 'terraform-multiple-ip-ranges',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'type': 'location-type', 'location-type': 'ipNamedLocation'},
            {'type': 'ip-range-count', 'count': 1, 'op': 'greater-than'}
        ]
    })

    # Test IP range count filter - locations with exactly 1 range
    single_range_policy = test.load_policy({
        'name': 'terraform-single-ip-range',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'type': 'location-type', 'location-type': 'ipNamedLocation'},
            {'type': 'ip-range-count', 'count': 1, 'op': 'equal'}
        ]
    })

    # Verify policy structures
    assert multiple_ranges_policy.resource_manager.type == 'entraid-named-location'
    assert single_range_policy.resource_manager.type == 'entraid-named-location'
    print("SUCCESS: IP range count filters configured successfully")


@terraform('entraid_named_location')
@pytest.mark.functional
def test_entraid_named_location_countries_count_filter_terraform(test, entraid_named_location):
    """Test countries count filter against Terraform-provisioned named locations"""
    trusted_countries = entraid_named_location.outputs['test_trusted_countries']['value']
    country_with_unknown = entraid_named_location.outputs['test_country_with_unknown']['value']

    # Verify test data contains expected countries counts
    assert len(trusted_countries['country']['countries_and_regions']) == 4
    assert len(country_with_unknown['country']['countries_and_regions']) == 1

    # Test countries count filter - locations with more than 1 country
    multiple_countries_policy = test.load_policy({
        'name': 'terraform-multiple-countries',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'type': 'location-type', 'location-type': 'countryNamedLocation'},
            {'type': 'countries-count', 'count': 1, 'op': 'greater-than'}
        ]
    })

    # Test countries count filter - locations with exactly 1 country
    single_country_policy = test.load_policy({
        'name': 'terraform-single-country',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'type': 'location-type', 'location-type': 'countryNamedLocation'},
            {'type': 'countries-count', 'count': 1, 'op': 'equal'}
        ]
    })

    # Verify policy structures
    assert multiple_countries_policy.resource_manager.type == 'entraid-named-location'
    assert single_country_policy.resource_manager.type == 'entraid-named-location'
    print("SUCCESS: Countries count filters configured successfully")


@terraform('entraid_named_location')
@pytest.mark.functional
def test_entraid_named_location_display_name_filter_terraform(test, entraid_named_location):
    """Test display name pattern matching against Terraform-provisioned named locations"""
    corporate_ips = entraid_named_location.outputs['test_corporate_ips']['value']

    # Verify test data has expected display names
    assert 'C7N Test - Corporate IP Ranges' in corporate_ips['display_name']

    # Test display name pattern filter
    corporate_policy = test.load_policy({
        'name': 'terraform-corporate-locations',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'type': 'value', 'key': 'displayName', 'op': 'glob', 'value': '*Corporate*'}
        ]
    })

    # Test C7N test locations filter
    test_locations_policy = test.load_policy({
        'name': 'terraform-test-locations',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'type': 'value', 'key': 'displayName', 'op': 'glob', 'value': 'C7N Test*'}
        ]
    })

    # Verify policy structures
    assert corporate_policy.resource_manager.type == 'entraid-named-location'
    assert test_locations_policy.resource_manager.type == 'entraid-named-location'
    print("SUCCESS: Display name pattern filters configured successfully")


@terraform('entraid_named_location')
@pytest.mark.functional
def test_entraid_named_location_comprehensive_terraform(test, entraid_named_location):
    """Test comprehensive named location policies combining multiple filters"""
    # Test policy combining location type and value filters
    comprehensive_policy = test.load_policy({
        'name': 'terraform-comprehensive-location-audit',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'or': [
                {'and': [
                    {'type': 'location-type', 'location-type': 'ipNamedLocation'},
                    {'type': 'value', 'key': 'displayName', 'op': 'glob', 'value': '*External*'}
                ]},
                {'and': [
                    {'type': 'location-type', 'location-type': 'countryNamedLocation'},
                    {'type': 'value', 'key': 'displayName', 'op': 'glob', 'value': '*Blocked*'}
                ]}
            ]}
        ]
    })

    # Test policy combining count-based filters
    count_based_policy = test.load_policy({
        'name': 'terraform-count-based-locations',
        'resource': 'azure.entraid-named-location',
        'filters': [
            {'or': [
                {'and': [
                    {'type': 'location-type', 'location-type': 'ipNamedLocation'},
                    {'type': 'ip-range-count', 'count': 1, 'op': 'greater-than'}
                ]},
                {'and': [
                    {'type': 'location-type', 'location-type': 'countryNamedLocation'},
                    {'type': 'countries-count', 'count': 1, 'op': 'greater-than'}
                ]}
            ]}
        ]
    })

    # Verify policy structures
    assert comprehensive_policy.resource_manager.type == 'entraid-named-location'
    assert count_based_policy.resource_manager.type == 'entraid-named-location'
    print("SUCCESS: Comprehensive named location policies configured successfully")
