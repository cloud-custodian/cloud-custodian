#!/usr/bin/env python3
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import unittest
import sys
from unittest.mock import Mock, patch

try:
    from c7n_azure.resources.entraid_user import EntraIDUser
    from c7n_azure.resources.entraid_group import EntraIDGroup
    from c7n.config import Config
    from c7n.policy import Policy
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)


class EntraIDUserTest(unittest.TestCase):
    """Test EntraID User resource functionality"""

    def load_policy(self, policy_data, validate=False):
        """Helper method to load a policy"""
        config = Config.empty()
        policy = Policy(policy_data, config, session_factory=None)
        return policy

    def test_entraid_user_schema_validate(self):
        """Test that the EntraID user resource schema validates correctly"""
        policy_data = {
            'name': 'test-entraid-user',
            'resource': 'azure.entraid-user',
            'filters': [
                {'type': 'value', 'key': 'accountEnabled', 'value': True}
            ]
        }
        p = self.load_policy(policy_data, validate=True)
        self.assertIsNotNone(p)
        self.assertEqual(p.name, 'test-entraid-user')

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
        mock_session.return_value.get_session_for_resource.return_value = mock_client

        # Sample user data
        users = [
            {
                'objectId': 'user1-id',
                'displayName': 'Test User',
                'userPrincipalName': 'test.user@example.com',
                'accountEnabled': True,
                'signInActivity': {'lastSignInDateTime': '2023-01-01T12:00:00Z'},
                'lastPasswordChangeDateTime': '2022-01-01T12:00:00Z',
                'jobTitle': 'Administrator'
            },
            {
                'objectId': 'user2-id',
                'displayName': 'Regular User',
                'userPrincipalName': 'regular@example.com',
                'accountEnabled': False,
                'signInActivity': {},
                'lastPasswordChangeDateTime': None,
                'jobTitle': 'User'
            }
        ]

        policy_data = {
            'name': 'test-augment',
            'resource': 'azure.entraid-user'
        }
        policy = self.load_policy(policy_data)

        resource_mgr = policy.resource_manager
        augmented = resource_mgr.augment(users)

        # Check augmented fields
        self.assertIn('c7n:LastSignInDays', augmented[0])
        self.assertIn('c7n:IsHighPrivileged', augmented[0])
        self.assertIn('c7n:PasswordAge', augmented[0])

        # Admin user should be flagged as high privileged
        self.assertTrue(augmented[0]['c7n:IsHighPrivileged'])
        self.assertFalse(augmented[1]['c7n:IsHighPrivileged'])

    @patch('c7n_azure.resources.entraid_user.local_session')
    def test_auth_methods_filter(self, mock_session):
        """Test authentication methods filter"""
        # Mock the session and Graph API responses
        mock_client = Mock()
        mock_session.return_value.get_session_for_resource.return_value = mock_client

        users = [
            {
                'objectId': 'user1',
                'id': 'user1'
            },
            {
                'objectId': 'user2',
                'id': 'user2'
            },
            {
                'objectId': 'user3',
                'id': 'user3'
            }
        ]

        policy_data = {
            'name': 'test-auth-methods-filter',
            'resource': 'azure.entraid-user',
            'filters': [
                {'type': 'auth-methods', 'key': '[]."@odata.type"', 'value': 'not-null'}
            ]
        }

        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager

        # Mock the Graph API responses for authentication methods
        def mock_make_graph_request(endpoint):
            if 'user1/authentication/methods' in endpoint:
                return {
                    'value': [
                        {
                            '@odata.type': (
                                '#microsoft.graph.'
                                'microsoftAuthenticatorAuthenticationMethod'
                            ),
                            'id': 'method1-id',
                            'displayName': 'Microsoft Authenticator'
                        },
                        {
                            '@odata.type': (
                                '#microsoft.graph.phoneAuthenticationMethod'
                            ),
                            'id': 'method2-id',
                            'phoneNumber': '+1555XXXX123',
                            'phoneType': 'mobile'
                        }
                    ]
                }
            elif 'user2/authentication/methods' in endpoint:
                return {
                    'value': [
                        {
                            '@odata.type': '#microsoft.graph.phoneAuthenticationMethod',
                            'id': 'method3-id',
                            'phoneNumber': '+1555XXXX456',
                            'phoneType': 'mobile'
                        }
                    ]
                }
            else:
                return {'value': []}

        resource_mgr.make_graph_request = mock_make_graph_request

        filtered = resource_mgr.filter_resources(users)

        # Should have all 3 users - the filter enriches all users with auth methods data
        self.assertEqual(len(filtered), 2)
        self.assertIn('c7n:AuthMethods', filtered[0])
        self.assertIn('c7n:AuthMethods', filtered[1])

        # Check that auth methods data is properly enriched
        user1_methods = next(u for u in filtered if u['objectId'] == 'user1')['c7n:AuthMethods']
        user2_methods = next(u for u in filtered if u['objectId'] == 'user2')['c7n:AuthMethods']

        self.assertEqual(len(user1_methods), 2)  # User1 has 2 auth methods
        self.assertEqual(len(user2_methods), 1)  # User2 has 1 auth method

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

        policy_data = {
            'name': 'test-signin-filter',
            'resource': 'azure.entraid-user',
            'filters': [
                {'type': 'last-sign-in', 'days': 90, 'op': 'greater-than'}
            ]
        }

        policy = self.load_policy(policy_data)
        resource_mgr = policy.resource_manager
        filtered = resource_mgr.filter_resources(users)

        # Should match user1 and user3 (>90 days)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(
            set(u['objectId'] for u in filtered), {'user1', 'user3'}
        )


class EntraIDGroupTest(unittest.TestCase):
    """Test EntraID Group resource functionality"""

    def load_policy(self, policy_data, validate=False):
        """Helper method to load a policy"""
        config = Config.empty()
        policy = Policy(policy_data, config, session_factory=None)
        return policy

    def test_entraid_group_schema_validate(self):
        """Test that the EntraID group resource schema validates correctly"""
        policy_data = {
            'name': 'test-entraid-group',
            'resource': 'azure.entraid-group',
            'filters': [
                {'type': 'value', 'key': 'securityEnabled', 'value': True}
            ]
        }
        p = self.load_policy(policy_data, validate=True)
        self.assertIsNotNone(p)

    def test_entraid_group_resource_type(self):
        """Test EntraID group resource type configuration"""
        resource_type = EntraIDGroup.resource_type
        self.assertEqual(resource_type.service, 'graph')
        self.assertEqual(resource_type.id, 'id')
        self.assertEqual(resource_type.name, 'displayName')
        self.assertTrue(resource_type.global_resource)
        self.assertIn('Group.Read.All', resource_type.permissions)

    @patch('c7n_azure.graph_utils.local_session')
    def test_entraid_group_augment(self, mock_session):
        """Test group resource augmentation with computed fields"""
        mock_session.return_value.get_session_for_resource.return_value = Mock()

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
            }
        ]

        policy_data = {
            'name': 'test-augment',
            'resource': 'azure.entraid-group'
        }

        policy = self.load_policy(policy_data)
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
