# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import requests

from c7n.filters import Filter
from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.graph_utils import (
    GraphResourceManager, GraphTypeInfo, GraphSource, EntraIDDiagnosticSettingsFilter
)

log = logging.getLogger('custodian.azure.entraid.organization')


@resources.register('entraid-organization')
class EntraIDOrganization(GraphResourceManager):
    """EntraID Organization resource for tenant-level settings.

    Provides access to organization-level configuration.

    Permissions: See Graph API Permissions Reference section.

    Available filters: value, security-defaults

    :example:

    Check if security defaults are disabled:

    .. code-block:: yaml

        policies:
          - name: security-defaults-check
            resource: azure.entraid-organization
            filters:
              - type: security-defaults
                enabled: false

    Check if password lockout threshold exceeds 10 attempts:

    .. code-block:: yaml

        policies:
          - name: lockout-threshold-compliance
            resource: azure.entraid-organization
            filters:
              - type: password-lockout-threshold
                max_threshold: 10
    """

    def __init__(self, ctx, data):
        super().__init__(ctx, data)
        # Use our custom GraphSource instead of the default source
        self.source = GraphSource(self)

    class resource_type(GraphTypeInfo):
        doc_groups = ['EntraID', 'Identity']
        enum_spec = ('organization', 'list', None)
        id = 'id'
        name = 'displayName'
        date = 'createdDateTime'
        default_report_fields = (
            'displayName',
            'id',
            'createdDateTime',
            'verifiedDomains'
        )
        permissions = ('Organization.Read.All', 'Directory.Read.All')

    def make_graph_request(self, endpoint, method='GET'):
        """Override to use beta API for directory settings endpoints."""
        if endpoint.startswith('settings') or endpoint.startswith('directorySettingTemplates'):
            # Directory settings require beta API
            try:
                session = self.get_client()
                session._initialize_session()
                from c7n_azure.graph_utils import get_required_permissions_for_endpoint
                try:
                    get_required_permissions_for_endpoint(endpoint, method)
                except ValueError:
                    log.error(f"Cannot make Graph API request to unmapped endpoint: {endpoint}")
                    raise
                scope = 'https://graph.microsoft.com/.default'
                token = session.credentials.get_token(scope)
                headers = {
                    'Authorization': f'Bearer {token.token}',
                    'Content-Type': 'application/json'
                }
                # Use beta API for directory settings
                url = f'https://graph.microsoft.com/beta/{endpoint}'
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                log.error(f"Microsoft Graph beta API request failed for {endpoint}: {e}")
                raise
        else:
            # Use parent's v1.0 implementation for other endpoints
            return super().make_graph_request(endpoint, method)

    def get_graph_resources(self):
        """Get resources from Microsoft Graph API for use with GraphSource."""
        try:
            response = self.make_graph_request('organization')
            resources = response.get('value', [])

            log.debug(f"Retrieved {len(resources)} organization settings from Graph API")
            return resources
        except Exception as e:
            log.error(f"Error retrieving organization settings: {e}")
            return []


@EntraIDOrganization.filter_registry.register('security-defaults')
class SecurityDefaultsFilter(Filter):
    """Filter based on security defaults configuration.

    :example:

    Find organizations with security defaults disabled:

    .. code-block:: yaml

        policies:
          - name: security-defaults-disabled
            resource: azure.entraid-organization
            filters:
              - type: security-defaults
                enabled: false
    """

    schema = type_schema('security-defaults', enabled={'type': 'boolean'})

    def process(self, resources, event=None):  # pylint: disable=unused-argument
        enabled_required = self.data.get('enabled', True)
        filtered = []
        for resource in resources:
            security_defaults = resource.get('securityDefaults', {})
            is_enabled = security_defaults.get('isEnabled', False)
            if bool(is_enabled) == bool(enabled_required):
                filtered.append(resource)
        return filtered


@EntraIDOrganization.filter_registry.register('password-lockout-threshold')
class PasswordLockoutThresholdFilter(Filter):
    """Filter based on password lockout threshold configuration.

    Checks the account lockout threshold setting from Directory Settings.
    Requires Microsoft Graph beta API and Directory.Read.All permission.

    :example:

    Find organizations where lockout threshold is greater than 10:

    .. code-block:: yaml

        policies:
          - name: lockout-threshold-too-high
            resource: azure.entraid-organization
            filters:
              - type: password-lockout-threshold
                max_threshold: 10
    """

    schema = type_schema('password-lockout-threshold', max_threshold={'type': 'integer'})

    def _get_password_rule_template_id(self):
        """Get the Password Rule Settings template ID dynamically."""
        try:
            # Query all directory setting templates first
            endpoint = "directorySettingTemplates"
            response = self.manager.make_graph_request(endpoint)
            templates = response.get('value', [])

            # Search for password-related template by displayName
            password_template = None
            for template in templates:
                display_name = template.get('displayName', '')
                # Look for common password policy template names
                if any(keyword in display_name.lower() for keyword in
                       ['password', 'lockout', 'authentication']):
                    password_template = template
                    log.debug(f"Found password template: {display_name}")
                    break

            if not password_template:
                # Log available templates for debugging
                template_names = [t.get('displayName', 'Unknown') for t in templates]
                log.error(
                    f"No password-related template found. Available templates: {template_names}")
                return None

            template_id = password_template.get('id')
            if not template_id:
                log.error("Password template ID not found")
                return None

            log.debug(f"Found password template ID: {template_id}")
            return template_id

        except Exception as e:
            log.error(f"Error retrieving password template: {e}")
            return None

    def process(self, resources, event=None):  # pylint: disable=unused-argument
        max_threshold = self.data.get('max_threshold', 10)
        filtered = []

        # Get the Password Rule Settings template ID dynamically
        template_id = self._get_password_rule_template_id()
        if not template_id:
            log.warning("Cannot proceed without Password Rule Settings template ID")
            return filtered

        for resource in resources:
            try:
                # Query directory settings
                settings_response = self.manager.make_graph_request('settings')
                settings_list = settings_response.get('value', [])

                # Find Password Rule Settings by template ID
                password_settings = None
                for setting in settings_list:
                    if setting.get('templateId') == template_id:
                        password_settings = setting
                        break

                if not password_settings:
                    log.warning("Password Rule Settings not found in directory settings")
                    continue

                # Extract LockoutThreshold from settings values
                lockout_threshold = None
                values = password_settings.get('values', [])

                for value in values:
                    if value.get('name') == 'LockoutThreshold':
                        try:
                            lockout_threshold = int(value.get('value', '0'))
                        except (ValueError, TypeError):
                            log.warning(f"Invalid LockoutThreshold value: {value.get('value')}")
                            continue
                        break

                if lockout_threshold is None:
                    log.warning("LockoutThreshold not found in Password Rule Settings")
                    continue

                # Apply filter logic - include if threshold exceeds max_threshold
                if lockout_threshold > max_threshold:
                    # Add lockout threshold info to resource for reporting
                    resource['lockoutThreshold'] = lockout_threshold
                    filtered.append(resource)

            except Exception as e:
                log.error(f"Error checking password lockout threshold: {e}")
                continue

        return filtered


# Register diagnostic settings filter for EntraID organization
EntraIDOrganization.filter_registry.register('diagnostic-settings', EntraIDDiagnosticSettingsFilter)
