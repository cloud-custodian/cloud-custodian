# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n_azure.provider import resources
from c7n_azure.graph_utils import (
    GraphResourceManager, GraphTypeInfo, GraphSource, EntraIDDiagnosticSettingsFilter
)

log = logging.getLogger('custodian.azure.entraid.authorization_policy')


@resources.register('entraid-authorization-policy')
class EntraIDAuthorizationPolicy(GraphResourceManager):
    """EntraID Authorization Policy resource for tenant-level authorization settings.

    Provides access to organization-level authorization configuration including
    default user role permissions such as the ability to create applications.

    Permissions: Policy.Read.All

    Available filters: value, allowed-to-create-apps

    :example:

    Check if users can register applications (CIS-B-MAF-4.0.0-6.14):

    .. code-block:: yaml

        policies:
          - name: users-can-register-applications-check
            resource: azure.entraid-authorization-policy
            filters:
              - type: allowed-to-create-apps
                value: true

    Check multiple default user role permissions:

    .. code-block:: yaml

        policies:
          - name: default-user-permissions-audit
            resource: azure.entraid-authorization-policy
            filters:
              - type: value
                key: defaultUserRolePermissions.allowedToCreateApps
                value: false
              - type: value
                key: defaultUserRolePermissions.allowedToCreateSecurityGroups
                value: false
    """

    def __init__(self, ctx, data):
        super().__init__(ctx, data)
        # Use our custom GraphSource instead of the default source
        self.source = GraphSource(self)

    class resource_type(GraphTypeInfo):
        doc_groups = ['EntraID', 'Identity', 'Authorization']
        enum_spec = ('policies/authorizationPolicy', 'get', None)
        id = 'id'
        name = 'displayName'
        date = None  # Authorization policy doesn't have a creation date
        default_report_fields = (
            'id',
            'displayName',
            'description',
            'defaultUserRolePermissions'
        )
        permissions = ('Policy.Read.All',)

    def get_graph_resources(self):
        """Get authorization policy from Microsoft Graph API."""
        try:
            # The authorization policy endpoint returns a single object, not a collection
            response = self.make_graph_request('policies/authorizationPolicy')

            # Wrap single policy in a list for consistent processing
            if response:
                resources = [response]
                log.debug("Retrieved authorization policy from Graph API")
                return resources
            else:
                log.warning("No authorization policy data received from Graph API")
                return []

        except Exception as e:
            log.error(f"Error retrieving authorization policy: {e}")
            if "Insufficient privileges" in str(e) or "403" in str(e):
                log.error(
                    "Insufficient privileges to read authorization policy. "
                    "Required permissions: Policy.Read.All"
                )
            return []


# Register diagnostic settings filter for EntraID authorization policy
EntraIDAuthorizationPolicy.filter_registry.register(
    'diagnostic-settings', EntraIDDiagnosticSettingsFilter
)
