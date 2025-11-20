# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import requests

from c7n.filters import Filter
from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.graph_utils import (GraphResourceManager, GraphTypeInfo, GraphSource,
                                   get_required_permissions_for_endpoint)

log = logging.getLogger('custodian.azure.entraid.conditional_access')


@resources.register('entraid-conditional-access-policy')
class EntraIDConditionalAccessPolicy(GraphResourceManager):
    """EntraID Conditional Access Policy resource.

    Manages conditional access policies. Requires Microsoft Graph beta API.
    Permissions: See Graph API Permissions Reference section.

    Available filters: value, admin-mfa-required

    :example:

    Find disabled policies or policies not requiring MFA for admins:

    .. code-block:: yaml

        policies:
          - name: disabled-ca-policies
            resource: azure.entraid-conditional-access-policy
            filters:
              - type: value
                key: state
                value: disabled
          - name: admin-no-mfa-policies
            resource: azure.entraid-conditional-access-policy
            filters:
              - type: admin-mfa-required
                value: false
    """

    def __init__(self, ctx, data):
        super().__init__(ctx, data)
        # Use our custom GraphSource instead of the default source
        self.source = GraphSource(self)

    class resource_type(GraphTypeInfo):
        doc_groups = ['EntraID', 'Identity', 'Security']
        enum_spec = ('identity/conditionalAccess/policies', 'list', None)
        id = 'id'
        name = 'displayName'
        date = 'createdDateTime'
        default_report_fields = (
            'displayName',
            'state',
            'createdDateTime',
            'modifiedDateTime'
        )
        permissions = ('Policy.Read.All',)

    def make_graph_request(self, endpoint, method='GET'):
        """Make a request to Microsoft Graph API with minimum required permissions."""
        try:
            session = self.get_client()
            session._initialize_session()

            # Get specific permissions for this endpoint instead of using .default
            try:
                get_required_permissions_for_endpoint(endpoint, method)
            except ValueError:
                log.error(f"Cannot make Graph API request to unmapped endpoint: {endpoint}")
                raise

            # Request token for Microsoft Graph API
            scope = 'https://graph.microsoft.com/.default'

            token = session.credentials.get_token(scope)

            headers = {
                'Authorization': f'Bearer {token.token}',
                'Content-Type': 'application/json'
            }

            # Note: Conditional Access Policies require beta API
            url = f'https://graph.microsoft.com/beta/{endpoint}'
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            log.error(f"Microsoft Graph API request failed for {endpoint}: {e}")
            raise

    def get_graph_resources(self):
        """Get resources from Microsoft Graph API for use with GraphSource."""
        try:
            response = self.make_graph_request('identity/conditionalAccess/policies')
            resources = response.get('value', [])

            log.debug(f"Retrieved {len(resources)} conditional access policies from Graph API")
            return resources
        except Exception as e:
            log.warning(f"Could not retrieve Conditional Access Policies: {e}")

            log.warning(
                "Conditional Access Policies require Microsoft Graph beta API and "
                "appropriate permissions"
            )
            return []


@EntraIDConditionalAccessPolicy.filter_registry.register('admin-mfa-required')
class AdminMFARequiredFilter(Filter):
    """Filter conditional access policies based on MFA requirement for admins.

    :example:

    Find policies that don't require MFA for admin roles:

    .. code-block:: yaml

        policies:
          - name: admin-no-mfa
            resource: azure.entraid-conditional-access-policy
            filters:
              - type: admin-mfa-required
                value: false
    """

    schema = type_schema('admin-mfa-required', value={'type': 'boolean'})

    def process(self, resources, event=None):  # pylint: disable=unused-argument
        mfa_required = self.data.get('value', True)

        filtered = []
        for resource in resources:
            # Check if policy applies to admin roles and requires MFA
            conditions = resource.get('conditions', {})
            users = conditions.get('users', {})
            roles = users.get('includeRoles', [])

            grant_controls = resource.get('grantControls', {})
            built_in_controls = grant_controls.get('builtInControls', [])

            # Check if admin roles are included and MFA is required
            admin_roles = [
                'Global Administrator',
                'Privileged Role Administrator',
                'User Administrator'
            ]

            has_admin_roles = any(role in admin_roles for role in roles)
            requires_mfa = 'mfa' in [control.lower() for control in built_in_controls]

            if has_admin_roles:
                if ((mfa_required and requires_mfa) or
                        (not mfa_required and not requires_mfa)):
                    filtered.append(resource)

        return filtered
