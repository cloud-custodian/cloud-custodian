# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n.actions import BaseAction
from c7n.utils import type_schema
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
    Available actions: update

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


# Plain BaseAction rather than AzureBaseAction: this is one tenant-wide object with
# no resource group, and a failed PATCH should fail the run instead of being logged
# per resource. Same as the subscription singleton actions.
@EntraIDAuthorizationPolicy.action_registry.register('update')
class UpdateAuthorizationPolicy(BaseAction):
    """Update tenant authorization policy settings.

    Property names follow the Microsoft Graph authorizationPolicy resource. Only
    supplied properties are updated, including inside
    ``defaultUserRolePermissions``.

    ``permissionGrantPoliciesAssigned`` replaces the whole list. That includes
    the ``ManagePermissionGrantsForOwnedResource.*`` entries, which let owners
    consent for their own teams and chats, so list any entries to keep. An empty
    list turns off all user consent. Graph does not preserve the order of that
    list, so filter on membership rather than comparing whole lists.

    Permissions: Policy.ReadWrite.Authorization

    :example:

    Stop default users from registering applications (CIS-B-MAF-4.0.0-6.14):

    .. code-block:: yaml

        policies:
          - name: users-cannot-register-applications
            resource: azure.entraid-authorization-policy
            filters:
              - type: value
                key: defaultUserRolePermissions.allowedToCreateApps
                value: true
            actions:
              - type: update
                properties:
                  defaultUserRolePermissions:
                    allowedToCreateApps: false
    """

    schema = type_schema(
        'update',
        required=['properties'],
        properties={
            'type': 'object',
            'minProperties': 1,
            'additionalProperties': False,
            'properties': {
                'allowEmailVerifiedUsersToJoinOrganization': {'type': 'boolean'},
                'allowInvitesFrom': {'enum': [
                    'none',
                    'adminsAndGuestInviters',
                    'adminsGuestInvitersAndAllMembers',
                    'everyone',
                ]},
                'allowUserConsentForRiskyApps': {'type': 'boolean'},
                'allowedToSignUpEmailBasedSubscriptions': {'type': 'boolean'},
                'allowedToUseSSPR': {'type': 'boolean'},
                'blockMsolPowerShell': {'type': 'boolean'},
                # User, Guest User and Restricted Guest User role template ids
                'guestUserRoleId': {'enum': [
                    'a0b1b346-4d3e-4e8b-98f8-753987be4970',
                    '10dae51f-b6af-4016-8d66-8c2a99b929b3',
                    '2af84b1e-32c8-42b7-82bc-daa82404023b',
                ]},
                # allowedToReadOtherUsers is left out: Microsoft documents that it
                # must never be set to false.
                'defaultUserRolePermissions': {
                    'type': 'object',
                    'minProperties': 1,
                    'additionalProperties': False,
                    'properties': {
                        'allowedToCreateApps': {'type': 'boolean'},
                        'allowedToCreateSecurityGroups': {'type': 'boolean'},
                        'allowedToCreateTenants': {'type': 'boolean'},
                        'allowedToReadBitlockerKeysForOwnedDevice': {'type': 'boolean'},
                        'permissionGrantPoliciesAssigned': {
                            'type': 'array',
                            'uniqueItems': True,
                            'items': {'type': 'string'},
                        },
                    },
                },
            },
        },
    )
    permissions = ('Policy.ReadWrite.Authorization',)

    def process(self, resources):
        # The policy is a tenant singleton, so one PATCH covers every match
        self.manager.make_graph_request(
            'policies/authorizationPolicy', method='PATCH', data=self.data['properties'])
        self.log.info("Updated authorization policy: %s", self.data['properties'])
