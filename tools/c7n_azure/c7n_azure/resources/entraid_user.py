# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import requests
from datetime import datetime

from c7n.filters import Filter, ValueFilter
from c7n.utils import local_session, type_schema
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.constants import MSGRAPH_RESOURCE_ID
from c7n_azure.provider import resources
from c7n_azure.graph_utils import (
    GraphResourceManager, GraphTypeInfo, GraphSource,
    EntraIDDiagnosticSettingsFilter
)

log = logging.getLogger('custodian.azure.entraid.user')


@resources.register('entraid-user')
class EntraIDUser(GraphResourceManager):
    """EntraID User resource for managing users.

    Supports filtering by user properties, authentication methods, group memberships,
    and security settings. See Common EntraID Examples section for additional patterns.

    Available filters: value, auth-methods, risk-level, last-sign-in, group-membership, password-age
    Available actions: disable, require-mfa

    Permissions: See Graph API Permissions Reference section.

    :example:

    Find users with multiple security issues:

    .. code-block:: yaml

        policies:
          - name: high-risk-users-no-mfa
            resource: azure.entraid-user
            filters:
              - type: mfa-enabled
                value: false
              - type: risk-level
                value: high
            actions:
              - type: require-mfa
    """

    def __init__(self, ctx, data):
        super().__init__(ctx, data)
        # Use our custom GraphSource instead of the default source
        self.source = GraphSource(self)

    class resource_type(GraphTypeInfo):
        doc_groups = ['EntraID', 'Identity']
        enum_spec = ('users', 'list', None)
        detail_spec = ('users', 'get', 'id')
        id = 'id'
        name = 'displayName'
        date = 'createdDateTime'
        default_report_fields = (
            'displayName',
            'userPrincipalName',
            'mail',
            'accountEnabled',
            'userType',
            'createdDateTime',
            'lastSignInDateTime',
            'id'
        )
        permissions = (
            'User.Read.All',
            'UserAuthenticationMethod.Read.All',
            'IdentityRiskyUser.Read.All',
            'GroupMember.Read.All'

        )

    def get_graph_resources(self):
        """Get resources from Microsoft Graph API for use with GraphSource."""
        try:
            # Request specific fields including userType which is not returned by default
            # This ensures ValueFilter can work with userType field for guest user filtering
            # Note: Some fields like signInActivity and lastPasswordChangeDateTime may require
            # additional permissions, so we use a more conservative field selection
            select_fields = [
                'id', 'displayName', 'userPrincipalName', 'mail',
                'accountEnabled', 'createdDateTime', 'jobTitle', 'department', 'userType'
            ]
            endpoint = f"users?$select={','.join(select_fields)}"
            response = self.make_graph_request(endpoint)
            resources = response.get('value', [])

            log.debug(f"Retrieved {len(resources)} users from Graph API")

            # Augment resources with additional computed fields
            resources = self.augment(resources)

            log.debug(f"Returning {len(resources)} users after augmentation")
            return resources
        except Exception as e:
            log.error(f"Error retrieving EntraID users: {e}")
            if "Insufficient privileges" in str(e) or "403" in str(e):
                log.error(
                    "Insufficient privileges to read users. Required permissions: User.Read.All"
                )
            return []

    def augment(self, resources):
        """Augment user resources with additional Graph API data"""
        try:
            # Enhance with additional properties
            for resource in resources:
                # Add computed fields for policy evaluation
                resource['c7n:LastSignInDays'] = self._calculate_last_signin_days(resource)
                resource['c7n:IsHighPrivileged'] = self._is_high_privileged_user(resource)
                resource['c7n:PasswordAge'] = self._calculate_password_age(resource)

        except Exception as e:
            log.warning(f"Failed to augment EntraID users: {e}")

        return resources

    def _calculate_last_signin_days(self, user):
        """Calculate days since last sign-in"""
        if not user.get('signInActivity', {}).get('lastSignInDateTime'):
            return 999  # Large number for never signed in

        try:
            last_signin = datetime.fromisoformat(
                user['signInActivity']['lastSignInDateTime'].replace('Z', '+00:00')
            )
            return (
                datetime.now().replace(tzinfo=last_signin.tzinfo) - last_signin
            ).days
        except Exception:
            return 999

    def _is_high_privileged_user(self, user):
        """Determine if user has high privileges (to be enhanced with role checks)"""
        # This is a placeholder - would need additional Graph API calls for full implementation
        privileged_indicators = [
            user.get('userPrincipalName', '').endswith('admin@'),
            'admin' in (user.get('displayName') or '').lower(),
            'administrator' in (user.get('jobTitle') or '').lower()
        ]
        return any(privileged_indicators)

    def _calculate_password_age(self, user):
        """Calculate password age in days"""
        if not user.get('lastPasswordChangeDateTime'):
            return 0

        try:
            pwd_change = datetime.fromisoformat(
                user['lastPasswordChangeDateTime'].replace('Z', '+00:00')
            )
            return (
                datetime.now().replace(tzinfo=pwd_change.tzinfo) - pwd_change
            ).days
        except Exception:
            return 0

    def get_user_auth_methods(self, user_id):
        """Get user's authentication methods from Graph API.

        Returns the full list of authentication methods for the user.
        Required permission: UserAuthenticationMethod.Read.All
        """
        try:
            # Query user's authentication methods
            endpoint = f'users/{user_id}/authentication/methods'
            response = self.make_graph_request(endpoint)

            methods = response.get('value', [])
            return methods

        except requests.exceptions.RequestException as e:
            if "403" in str(e) or "Insufficient privileges" in str(e):
                log.warning(
                    f"Insufficient privileges to read authentication methods for user {user_id}. "
                    "Required permission: UserAuthenticationMethod.Read.All"
                )
                return None  # Unknown auth methods
            else:
                log.error(f"Error getting authentication methods for user {user_id}: {e}")
                return None

    def check_user_risk_level(self, user_id):
        """Check user's risk level using Identity Protection API.

        Required permission: IdentityRiskyUser.Read.All
        """
        try:
            # Query Identity Protection risky users endpoint
            endpoint = f'identityProtection/riskyUsers/{user_id}'
            response = self.make_graph_request(endpoint)

            # Extract risk level from response
            risk_level = response.get('riskLevel', 'none')

            # Map Graph API risk levels to our filter values
            risk_mapping = {
                'none': 'none',
                'low': 'low',
                'medium': 'medium',
                'high': 'high',
                'hidden': 'none',  # Treat hidden as none for filtering
                'unknownFutureValue': 'none'
            }

            return risk_mapping.get(risk_level.lower(), 'none')

        except requests.exceptions.RequestException as e:
            if "404" in str(e):
                # User not found in risky users - means no risk
                return 'none'
            elif "403" in str(e) or "Insufficient privileges" in str(e):
                log.warning(
                    f"Insufficient privileges to read risk level for user {user_id}. "
                    "Required permission: IdentityRiskyUser.Read.All"
                )
                return None  # Unknown risk level
            else:
                log.error(f"Error checking risk level for user {user_id}: {e}")
                return None

    def get_user_group_memberships(self, user_id):
        """Get user's group memberships from Graph API.

        Required permission: GroupMember.Read.All or Directory.Read.All
        """
        try:
            # Query user's group memberships (including transitive)
            endpoint = f'users/{user_id}/transitiveMemberOf'
            response = self.make_graph_request(endpoint)

            groups = response.get('value', [])

            # Extract group display names and IDs for filtering
            group_info = []
            for group in groups:
                # Only include actual groups (not directory roles)
                if group.get('@odata.type') == '#microsoft.graph.group':
                    group_info.append({
                        'id': group.get('id'),
                        'displayName': group.get('displayName', ''),
                        'mail': group.get('mail', '')
                    })

            return group_info

        except requests.exceptions.RequestException as e:
            if "403" in str(e) or "Insufficient privileges" in str(e):
                log.warning(
                    f"Insufficient privileges to read group memberships for user {user_id}. "
                    "Required permission: GroupMember.Read.All or Directory.Read.All"
                )
                return None  # Unknown group memberships
            else:
                log.error(f"Error getting group memberships for user {user_id}: {e}")
                return None


@EntraIDUser.filter_registry.register('auth-methods')
class AuthMethodsFilter(ValueFilter):
    """Filter users by authentication methods.

    Filters users based on their registered authentication methods.

    Requires: UserAuthenticationMethod.Read.All

    :example:

    .. code-block:: yaml

        filters:
          - type: auth-methods
            key: '[]."@odata.type"'
            op: contains
            value: '#microsoft.graph.microsoftAuthenticatorAuthenticationMethod'
    """

    schema = type_schema('auth-methods', rinherit=ValueFilter.schema)
    auth_methods_annotation_key = 'c7n:AuthMethods'
    annotate = False

    def __call__(self, i):
        if self.auth_methods_annotation_key not in i:
            # Get user's authentication methods from Graph API
            user_id = i.get('id') or i.get('objectId')
            auth_methods = self.manager.get_user_auth_methods(user_id)

            if auth_methods is None:
                # Unknown auth methods (permission error or API failure)
                # Skip this user to avoid false results
                log.warning(
                    f"Could not determine authentication methods for user "
                    f"{i.get('displayName', user_id)}"
                )
                auth_methods = []

            # Add auth methods to user resource for filtering
            i[self.auth_methods_annotation_key] = auth_methods

        return super().__call__(i[self.auth_methods_annotation_key])


@EntraIDUser.filter_registry.register('risk-level')
class RiskLevelFilter(Filter):
    """Filter users by Identity Protection risk level.

    Requires: IdentityRiskyUser.Read.All

    :example:

    .. code-block:: yaml

        filters:
          - type: risk-level
            value: high
    """

    schema = type_schema(
        'risk-level',
        value={'type': 'string', 'enum': ['none', 'low', 'medium', 'high']}
    )

    def process(self, resources, event=None):  # pylint: disable=unused-argument
        target_risk_level = self.data.get('value', 'none').lower()
        filtered = []

        for resource in resources:
            user_id = resource.get('id') or resource.get('objectId')
            if not user_id:
                log.warning(
                    f"Skipping user without ID: {resource.get('displayName', 'Unknown')}"
                )
                continue

            # Check actual risk level via Identity Protection API
            user_risk_level = self.manager.check_user_risk_level(user_id)

            if user_risk_level is None:
                # Unknown risk level (permission error or API failure)
                # Skip this user to avoid false results
                log.warning(
                    f"Could not determine risk level for user "
                    f"{resource.get('displayName', user_id)}"
                )
                continue

            if user_risk_level.lower() == target_risk_level:
                filtered.append(resource)

        return filtered


@EntraIDUser.filter_registry.register('last-sign-in')
class LastSignInFilter(Filter):
    """Filter users based on last sign-in activity.

    :example:

    Find users who haven't signed in for 90+ days:

    .. code-block:: yaml

        policies:
          - name: inactive-users
            resource: azure.entraid-user
            filters:
              - type: last-sign-in
                days: 90
                op: greater-than
    """

    schema = type_schema(
        'last-sign-in',
        days={'type': 'number'},
        op={'type': 'string', 'enum': ['greater-than', 'less-than', 'equal']}
    )

    def process(self, resources, event=None):  # pylint: disable=unused-argument
        days_threshold = self.data.get('days', 90)
        op = self.data.get('op', 'greater-than')

        filtered = []
        for resource in resources:
            last_signin_days = resource.get('c7n:LastSignInDays', 999)

            if op == 'greater-than' and last_signin_days > days_threshold:
                filtered.append(resource)
            elif op == 'less-than' and last_signin_days < days_threshold:
                filtered.append(resource)
            elif op == 'equal' and last_signin_days == days_threshold:
                filtered.append(resource)

        return filtered


@EntraIDUser.filter_registry.register('group-membership')
class GroupMembershipFilter(Filter):
    """Filter users based on group membership.

    Required permission: GroupMember.Read.All or Directory.Read.All

    :example:

    Find users in admin groups:

    .. code-block:: yaml

        policies:
          - name: admin-group-members
            resource: azure.entraid-user
            filters:
              - type: group-membership
                groups: ['Global Administrators', 'User Administrators']
                match: any
    """

    schema = type_schema(
        'group-membership',
        groups={'type': 'array', 'items': {'type': 'string'}},
        match={'type': 'string', 'enum': ['any', 'all']}
    )

    def process(self, resources, event=None):  # pylint: disable=unused-argument
        target_groups = self.data.get('groups', [])
        match_type = self.data.get('match', 'any')

        if not target_groups:
            return resources

        filtered = []
        for resource in resources:
            user_id = resource.get('id') or resource.get('objectId')
            if not user_id:
                log.warning(
                    f"Skipping user without ID: {resource.get('displayName', 'Unknown')}"
                )
                continue

            # Get actual group memberships via Graph API
            user_groups = self.manager.get_user_group_memberships(user_id)

            if user_groups is None:
                # Unknown group memberships (permission error or API failure)
                # Skip this user to avoid false results
                log.warning(
                    f"Could not determine group memberships for user "
                    f"{resource.get('displayName', user_id)}"
                )
                continue

            # Extract group names for matching
            group_names = [g.get('displayName', '') for g in user_groups]

            if match_type == 'any':
                if any(group in target_groups for group in group_names):
                    filtered.append(resource)
            elif match_type == 'all':
                if all(group in group_names for group in target_groups):
                    filtered.append(resource)

        return filtered


@EntraIDUser.filter_registry.register('password-age')
class PasswordAgeFilter(Filter):
    """Filter users based on password age.

    :example:

    Find users with passwords older than 180 days:

    .. code-block:: yaml

        policies:
          - name: old-password-users
            resource: azure.entraid-user
            filters:
              - type: password-age
                days: 180
                op: greater-than
    """

    schema = type_schema(
        'password-age',
        days={'type': 'number'},
        op={'type': 'string', 'enum': ['greater-than', 'less-than', 'equal']}
    )

    def process(self, resources, event=None):  # pylint: disable=unused-argument
        days_threshold = self.data.get('days', 90)
        op = self.data.get('op', 'greater-than')

        filtered = []
        for resource in resources:
            password_age = resource.get('c7n:PasswordAge', 0)

            if op == 'greater-than' and password_age > days_threshold:
                filtered.append(resource)
            elif op == 'less-than' and password_age < days_threshold:
                filtered.append(resource)
            elif op == 'equal' and password_age == days_threshold:
                filtered.append(resource)

        return filtered


@EntraIDUser.action_registry.register('disable')
class DisableUserAction(AzureBaseAction):
    """Disable EntraID users.

    :example:

    Disable inactive users:

    .. code-block:: yaml

        policies:
          - name: disable-inactive-users
            resource: azure.entraid-user
            filters:
              - type: last-sign-in
                days: 90
                op: greater-than
            actions:
              - type: disable
    """

    schema = type_schema('disable')
    permissions = ('User.ReadWrite.All',)

    def _prepare_processing(self):
        session = local_session(self.manager.session_factory)
        self.graph_session = session.get_session_for_resource(MSGRAPH_RESOURCE_ID)

    def _process_resource(self, resource):
        try:
            user_id = resource.get('id') or resource.get('objectId')
            display_name = resource.get('displayName', 'Unknown')

            if not user_id:
                self.log.error(f"Cannot disable user {display_name}: missing user ID")
                return

            # Make Graph API PATCH request to disable user
            # Use specific permission for user modification
            self.graph_session._initialize_session()
            token = self.graph_session.credentials.get_token(
                'https://graph.microsoft.com/User.ReadWrite.All'
            )

            headers = {
                'Authorization': f'Bearer {token.token}',
                'Content-Type': 'application/json'
            }

            # PATCH request to disable user account
            url = f'https://graph.microsoft.com/v1.0/users/{user_id}'
            data = {
                "accountEnabled": False
            }

            response = requests.patch(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()

            self.log.info(f"Successfully disabled user {display_name} ({user_id})")

        except requests.exceptions.RequestException as e:
            if "403" in str(e) or "Insufficient privileges" in str(e):
                self.log.error(
                    f"Insufficient privileges to disable user "
                    f"{resource.get('displayName', 'Unknown')}. "
                    "Required permission: User.ReadWrite.All"
                )
            else:
                self.log.error(
                    f"Failed to disable user {resource.get('displayName', 'Unknown')}: {e}"
                )
        except Exception as e:
            self.log.error(
                f"Failed to disable user {resource.get('displayName', 'Unknown')}: {e}"
            )


@EntraIDUser.action_registry.register('require-mfa')
class RequireMFAAction(AzureBaseAction):
    """Check MFA status for EntraID users and provide guidance.

    This action checks if users have MFA methods configured and provides
    recommendations for Conditional Access policy creation rather than
    attempting direct MFA enforcement.

    :example:

    Check MFA status for admin users:

    .. code-block:: yaml

        policies:
          - name: admin-mfa-status
            resource: azure.entraid-user
            filters:
              - type: group-membership
                groups: ['Global Administrators']
            actions:
              - type: require-mfa
    """

    schema = type_schema('require-mfa')
    permissions = ('UserAuthenticationMethod.Read.All',)

    def _prepare_processing(self):
        session = local_session(self.manager.session_factory)
        self.graph_session = session.get_session_for_resource(MSGRAPH_RESOURCE_ID)

    def _process_resource(self, resource):
        try:
            user_id = resource.get('id') or resource.get('objectId')
            display_name = resource.get('displayName', 'Unknown')

            if not user_id:
                self.log.error(f"Cannot check MFA for user {display_name}: missing user ID")
                return

            # Check if user has MFA methods configured using v1.0 API
            # Use specific permission for reading authentication methods
            self.graph_session._initialize_session()
            token = self.graph_session.credentials.get_token(
                'https://graph.microsoft.com/UserAuthenticationMethod.Read.All'
            )

            headers = {
                'Authorization': f'Bearer {token.token}',
                'Content-Type': 'application/json'
            }

            # Check user's authentication methods
            auth_methods_url = (
                f'https://graph.microsoft.com/v1.0/users/{user_id}/authentication/methods'
            )
            response = requests.get(auth_methods_url, headers=headers, timeout=30)
            response.raise_for_status()

            methods = response.json().get('value', [])
            mfa_methods = [m for m in methods if m.get('@odata.type') in [
                '#microsoft.graph.microsoftAuthenticatorAuthenticationMethod',
                '#microsoft.graph.phoneAuthenticationMethod',
                '#microsoft.graph.fido2AuthenticationMethod',
                '#microsoft.graph.windowsHelloForBusinessAuthenticationMethod'
            ]]

            if mfa_methods:
                self.log.info(
                    f"User {display_name} ({user_id}) already has "
                    f"{len(mfa_methods)} MFA method(s) configured"
                )
            else:
                self.log.warning(
                    f"User {display_name} ({user_id}) has no MFA methods configured. "
                    f"Consider creating a Conditional Access policy to enforce MFA registration."
                )

        except requests.exceptions.RequestException as e:
            if "403" in str(e) or "Insufficient privileges" in str(e):
                self.log.error(
                    f"Insufficient privileges to check MFA for user "
                    f"{resource.get('displayName', 'Unknown')}. "
                    "Required permission: UserAuthenticationMethod.Read.All"
                )
            else:
                self.log.error(
                    f"Failed to check MFA status for user "
                    f"{resource.get('displayName', 'Unknown')}: {e}"
                )
        except Exception as e:
            self.log.error(
                f"Failed to process MFA requirement for user "
                f"{resource.get('displayName', 'Unknown')}: {e}"
            )


# Register diagnostic settings filter for EntraID users
EntraIDUser.filter_registry.register(
    'diagnostic-settings', EntraIDDiagnosticSettingsFilter
)
