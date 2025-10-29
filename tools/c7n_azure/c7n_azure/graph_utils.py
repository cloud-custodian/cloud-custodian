# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import requests
import re

from c7n.utils import local_session, type_schema
from c7n.filters import ValueFilter
from c7n_azure.constants import MSGRAPH_RESOURCE_ID
from c7n_azure.query import QueryResourceManager, TypeInfo, TypeMeta, DescribeSource
from c7n_azure.provider import resources

log = logging.getLogger('custodian.azure.graph')


class GraphSource(DescribeSource):
    """Custom source for Microsoft Graph API resources.

    This source integrates with Cloud Custodian's filtering framework while
    using Microsoft Graph API instead of Azure Resource Manager APIs.
    """

    def get_resources(self, query=None):
        """Get resources from Microsoft Graph API."""
        try:
            # Use the manager's Graph API methods to retrieve resources
            return self.manager.get_graph_resources()
        except Exception as e:
            log.error(f"Error retrieving resources via Graph API: {e}")
            return []


# Microsoft Graph API Endpoint to Permissions Mapping
# This ensures we only request the minimum permissions needed for each operation
GRAPH_ENDPOINT_PERMISSIONS = {
    # User endpoints
    'users': ['User.Read.All'],
    'users/{id}': ['User.Read.All'],
    'users/{id}/authentication/methods': ['UserAuthenticationMethod.Read.All'],
    'users/{id}/transitiveMemberOf': ['GroupMember.Read.All'],
    # Identity Protection endpoints
    'identityProtection/riskyUsers/{id}': ['IdentityRiskyUser.Read.All'],

    # Group endpoints
    'groups': ['Group.Read.All'],
    'groups/{id}': ['Group.Read.All'],
    'groups/{id}/members': ['GroupMember.Read.All'],
    'groups/{id}/members/$count': ['GroupMember.Read.All'],
    'groups/{id}/owners': ['Group.Read.All'],
    'groups/{id}/owners/$count': ['Group.Read.All'],

    # Organization endpoints
    'organization': ['Organization.Read.All'],

    # Policy endpoints (require beta API)
    'identity/conditionalAccess/policies': ['Policy.Read.All'],
    'identity/conditionalAccess/namedLocations': ['Policy.Read.All'],
    'identity/conditionalAccess/namedLocations/{id}': ['Policy.Read.All'],
    'policies/identitySecurityDefaultsEnforcementPolicy': ['Policy.Read.All'],

    # Authorization Policy endpoints
    'policies/authorizationPolicy': ['Policy.Read.All'],

    # Directory Settings endpoints (beta API)
    'settings': ['Directory.Read.All'],
    'settings/{id}': ['Directory.ReadWrite.All'],
    'directorySettingTemplates': ['Directory.Read.All'],
}


def get_required_permissions_for_endpoint(endpoint, method='GET'):
    """Get the minimum required permissions for a Graph API endpoint."""
    # Normalize endpoint by replacing specific IDs with {id} placeholder
    normalized_endpoint = endpoint

    # Replace UUIDs and specific IDs with {id} placeholder for lookup
    normalized_endpoint = re.sub(r'/[0-9a-fA-F-]{8,}', '/{id}', normalized_endpoint)

    # For write operations, we need ReadWrite permissions
    if method in ['PATCH', 'POST', 'PUT', 'DELETE']:
        if 'users' in normalized_endpoint:
            return ['User.ReadWrite.All']
        elif 'groups' in normalized_endpoint:
            return ['Group.ReadWrite.All']
        elif 'authentication' in normalized_endpoint:
            return ['UserAuthenticationMethod.ReadWrite.All']

    # Check for exact match first
    if normalized_endpoint in GRAPH_ENDPOINT_PERMISSIONS:
        return GRAPH_ENDPOINT_PERMISSIONS[normalized_endpoint]

    # Check for pattern matches
    for pattern, permissions in GRAPH_ENDPOINT_PERMISSIONS.items():
        if pattern in normalized_endpoint:
            return permissions

    # Fail-fast for unmapped endpoints rather than using overprivileged .default
    log.error(
        f"No permissions mapping found for endpoint: {endpoint}. "
        f"This endpoint must be explicitly mapped in GRAPH_ENDPOINT_PERMISSIONS "
        f"to ensure minimum required permissions."
    )
    raise ValueError(
        f"Unmapped Graph API endpoint: {endpoint}. "
        f"Add permission mapping to prevent overprivileged access."
    )


class GraphTypeInfo(TypeInfo, metaclass=TypeMeta):
    """Type info for Microsoft Graph resources"""
    id = 'id'
    name = 'displayName'
    date = 'createdDateTime'
    global_resource = True
    service = 'graph'
    resource_endpoint = MSGRAPH_RESOURCE_ID
    diagnostic_settings_enabled = True

    @classmethod
    def extra_args(cls, parent_resource):
        return {}


class GraphResourceManager(QueryResourceManager):
    """Base class for Microsoft Graph API resources.

    Provides common Graph API client functionality for all EntraID resources.
    """

    def get_client(self):
        """Get Microsoft Graph client session"""
        session = local_session(self.session_factory)
        # Default to Microsoft Graph session for Graph operations
        return session.get_session_for_resource(MSGRAPH_RESOURCE_ID)

    def make_graph_request(self, endpoint, method='GET', data=None):
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
            # Note: Individual permissions like User.Read.All are enforced at
            # the app registration level
            # The scope for Microsoft Graph API should always be
            # https://graph.microsoft.com/.default
            scope = 'https://graph.microsoft.com/.default'

            token = session.credentials.get_token(scope)

            headers = {
                'Authorization': f'Bearer {token.token}',
                'Content-Type': 'application/json'
            }

            url = f'https://graph.microsoft.com/v1.0/{endpoint}'

            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'PATCH':
                response = requests.patch(url, headers=headers, json=data, timeout=30)
            else:
                response = requests.request(method, url, headers=headers, json=data, timeout=30)

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            log.error(f"Microsoft Graph API request failed for {endpoint}: {e}")
            raise

    @staticmethod
    def register_graph_specific(registry, resource_class):
        """Register Graph-specific filters and actions for Graph resource managers."""

        if not issubclass(resource_class, GraphResourceManager):
            return

        # Register EntraID-specific diagnostic settings filter if enabled
        if resource_class.resource_type.diagnostic_settings_enabled:
            resource_class.filter_registry.register(
                'diagnostic-settings', EntraIDDiagnosticSettingsFilter)


class EntraIDDiagnosticSettingsFilter(ValueFilter):
    """Diagnostic settings filter for EntraID resources.

    EntraID diagnostic settings are tenant-level and accessed via the microsoft.aadiam provider,
    not per-resource like ARM resources.
    """
    schema = type_schema('diagnostic-settings', rinherit=ValueFilter.schema)
    schema_alias = True
    log = logging.getLogger('custodian.azure.entraid.DiagnosticSettingsFilter')

    def process(self, resources, event=None):
        """Process EntraID resources by checking tenant-level diagnostic settings."""

        # Get tenant-level diagnostic settings
        session = local_session(self.manager.session_factory)
        session.client('azure.mgmt.monitor.MonitorManagementClient')

        # EntraID diagnostic settings are tenant-level:
        # /providers/microsoft.aadiam/diagnosticSettings
        tenant_diagnostic_settings = []
        try:
            # List all EntraID diagnostic settings for the tenant
            # Use the correct EntraID diagnostic settings API endpoint
            import requests
            session_token = session.get_credentials()
            token = session_token.get_token('https://management.azure.com/.default')

            headers = {
                'Authorization': f'Bearer {token.token}',
                'Content-Type': 'application/json'
            }

            # Use the correct EntraID diagnostic settings API endpoint from our research
            url = ('https://management.azure.com/providers/microsoft.aadiam/'
                   'diagnosticSettings?api-version=2017-04-01-preview')
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.json()
            tenant_diagnostic_settings = data.get('value', [])

            if not tenant_diagnostic_settings:
                tenant_diagnostic_settings = [{}]
        except requests.exceptions.HTTPError as e:
            errmsg = f"Failed to retrieve EntraID diagnostic settings: {e}."
            if response.status_code == 403:
                errmsg += " Ensure service principal has " \
                    "'Microsoft.AADIAM/diagnosticSettings/read' permission."
            self.log.error(errmsg)
            # If no settings available, use empty list so absent operator can function
            raise

        # Apply filter to diagnostic settings
        if not tenant_diagnostic_settings:
            tenant_diagnostic_settings = [{}]

        filtered_settings = super(EntraIDDiagnosticSettingsFilter, self).process(
            tenant_diagnostic_settings, event=None)

        # If diagnostic settings match the filter criteria, return all resources
        # since EntraID diagnostic settings apply to the entire tenant
        if filtered_settings:
            return resources
        else:
            return []


resources.subscribe(GraphResourceManager.register_graph_specific)
