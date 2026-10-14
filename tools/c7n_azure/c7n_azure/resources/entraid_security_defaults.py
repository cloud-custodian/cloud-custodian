# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n_azure.provider import resources
from c7n_azure.graph_utils import GraphResourceManager, GraphTypeInfo, GraphSource

log = logging.getLogger('custodian.azure.entraid.security_defaults')


@resources.register('entraid-security-defaults')
class EntraIDSecurityDefaults(GraphResourceManager):
    """EntraID Security Defaults resource.

    Manages the security defaults policy which provides pre-configured security
    settings that Microsoft manages for your directory.

    **Minimum Required Permissions:**
    - Policy.Read.All - Read security defaults policy configuration
    - Policy.ReadWrite.ConditionalAccess - Modify security defaults (actions only)

    **Security Note:** This resource requests ONLY EntraID security policy permissions.
    No direct access to SharePoint security settings, Exchange security policies,
    or Teams security settings.

    :example:

    Check if security defaults are enabled:

    .. code-block:: yaml

        policies:
          - name: check-security-defaults
            resource: azure.entraid-security-defaults
            filters:
              - type: value
                key: isEnabled
                value: true
    """

    def __init__(self, ctx, data):
        super().__init__(ctx, data)
        # Use our custom GraphSource instead of the default source
        self.source = GraphSource(self)

    class resource_type(GraphTypeInfo):
        doc_groups = ['EntraID', 'Identity', 'Security']
        enum_spec = ('policies/identitySecurityDefaultsEnforcementPolicy', 'get', None)
        id = 'id'
        name = 'displayName'
        default_report_fields = (
            'displayName',
            'isEnabled',
            'description'
        )
        permissions = ('Policy.Read.All',)

    def get_graph_resources(self):
        """Get resources from Microsoft Graph API for use with GraphSource."""
        try:
            # Security defaults policy endpoint
            policy = self.make_graph_request(
                'policies/identitySecurityDefaultsEnforcementPolicy'
            )

            log.debug("Retrieved security defaults policy from Graph API")
            return [policy]
        except Exception as e:
            log.warning(f"Could not retrieve Security Defaults policy: {e}")
            return []
