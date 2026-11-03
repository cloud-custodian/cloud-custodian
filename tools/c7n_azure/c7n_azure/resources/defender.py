# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from azure.mgmt.security.models import (
    NotificationsSourceAlert,
    NotificationsSourceAttackPath,
    SecurityContactPropertiesNotificationsByRole,
)

from c7n.exceptions import PolicyValidationError
from c7n.utils import type_schema
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager, QueryMeta, TypeInfo


@resources.register("defender-pricing")
class DefenderPricing(QueryResourceManager, metaclass=QueryMeta):
    """Active Microsoft Defender pricing details for supported resources.

    :example:

    Check if the Key Vaults resource is operating under the Standard
    pricing tier. This equates to Microsoft Defender being "On" in some
    security assessments.

    .. code-block:: yaml

        policies:
          - name: azure-defender-keyvaults-enabled
            resource: azure.defender-pricing
            filters:
              - name: KeyVaults
              - properties.pricingTier: Standard
    """

    class resource_type(TypeInfo):
        doc_groups = ["Security"]

        id = "id"
        name = "name"
        enum_spec = ("pricings", "list", None)
        client = "SecurityCenter"
        filter_name = None
        service = "azure.mgmt.security"
        resource_type = "Microsoft.Security/pricings"

        @classmethod
        def extra_args(cls, resource_manager):
            return {
                'scope_id': f'subscriptions/{resource_manager.get_session().get_subscription_id()}'
            }


@resources.register("defender-setting")
class DefenderSetting(QueryResourceManager, metaclass=QueryMeta):
    """Top-level Microsoft Defender settings for a subscription.

    :example:

    Check that the MCAS integration with Microsoft Defender is enabled.

    .. code-block:: yaml

        policies:
          - name: azure-defender-mcas-enabled
            resource: azure.defender-setting
            filters:
            - name: MCAS
            - kind: DataExportSettings
            - properties.enabled: True
    """

    class resource_type(TypeInfo):
        doc_groups = ["Security"]

        id = "id"
        name = "name"
        enum_spec = ("settings", "list", None)
        client = "SecurityCenter"
        filter_name = None
        service = "azure.mgmt.security"
        resource_type = "Microsoft.Security/settings"


@resources.register("defender-autoprovisioning")
class DefenderAutoProvisioningSetting(QueryResourceManager, metaclass=QueryMeta):
    """Auto-provisioning settings for Microsoft Defender agents.

    :example:

    Check that auto-provisioning is enabled for the Microsoft Defender monitoring agent.

    .. code-block:: yaml

        policies:
          - name: azure-defender-auto-provisioning-enabled
            resource: azure.defender-autoprovisioning
            filters:
            - name: default
            - properties.autoProvision: "On"
    """

    class resource_type(TypeInfo):
        doc_groups = ["Security"]

        id = "id"
        name = "name"
        enum_spec = ("auto_provisioning_settings", "list", None)
        client = "SecurityCenter"
        filter_name = None
        service = "azure.mgmt.security"
        resource_type = "Microsoft.Security/autoProvisioningSettings"


@resources.register("defender-alert")
class DefenderAlertSettings(QueryResourceManager, metaclass=QueryMeta):
    """Alert settings for Microsoft Defender.

    :example:

    Check that auto-provisioning is enabled for the Microsoft Defender monitoring agent.

    .. code-block:: yaml

        policies:
          - name: azure-defender-alert-enabled
            resource: azure.defender-alert
            filters:
            - name: default
            - properties.alertNotifications: "On"
    """

    class resource_type(TypeInfo):
        doc_groups = ["Security"]

        id = "id"
        name = "name"
        enum_spec = ("security_contacts", "list", None)
        client = "securityContacts"
        filter_name = None
        service = "azure.mgmt.security"
        resource_type = "Microsoft.Security/alertNotifications"


@resources.register("defender-assessment")
class DefenderAssessment(QueryResourceManager, metaclass=QueryMeta):
    class resource_type(TypeInfo):
        doc_groups = ["Security"]

        id = "id"
        name = "name"
        service = "azure.mgmt.security"
        client = "SecurityCenter"
        enum_spec = ("assessments", "list", None)
        resource_type = 'Microsoft.Security/assessments'
        default_report_fields = ["id", "name"]

        @classmethod
        def extra_args(cls, resource_manager):
            scope = '/subscriptions/{0}'\
                .format(resource_manager.get_session().get_subscription_id())
            return {'scope': scope}


@resources.register("defender-contact")
class DefenderSecurityContact(QueryResourceManager, metaclass=QueryMeta):
    """Security Contacts Resource

    :example:

    Finds security contacts with emails

    .. code-block:: yaml

        policies:
          - name: test-security-contacts
            resource: azure.defender-contact
            filters:
              - type: value
                key: properties.email
                value: null
                op: ne

    """
    class resource_type(TypeInfo):
        doc_groups = ["Security"]

        id = "id"
        name = "name"
        service = "azure.mgmt.security"
        client = "SecurityCenter"
        enum_spec = ("security_contacts", "list", None)
        resource_type = "Microsoft.Security/securityContacts"
        default_report_fields = ["id", "name"]

        @classmethod
        def extra_args(cls, resource_manager):
            # fix for https://github.com/Azure/azure-sdk-for-python/issues/35996
            return {'api_version': '2023-12-01-preview'}


@DefenderSecurityContact.action_registry.register('set-security-contact')
class SetSecurityContactAction(AzureBaseAction):
    """Update a Microsoft Defender for Cloud security contact.

    The underlying API replaces the whole security contact, so the current
    contact is read first and only the properties given in the action are
    changed. ``notifications-sources``, when given, replaces the existing
    list of sources.

    :example:

    Set the notification email on security contacts that have none.

    .. code-block:: yaml

        policies:
          - name: azure-defender-contact-email-remediate
            resource: azure.defender-contact
            filters:
              - type: value
                key: properties.emails
                value: empty
            actions:
              - type: set-security-contact
                emails:
                  - security@example.com
                is-enabled: true
                notifications-by-role:
                  state: "On"
                  roles:
                    - Owner
                notifications-sources:
                  - source-type: Alert
                    minimal-severity: High
    """

    schema = type_schema(
        'set-security-contact',
        **{
            'emails': {
                'oneOf': [
                    {'type': 'string', 'minLength': 1},
                    {
                        'type': 'array',
                        'items': {'type': 'string', 'minLength': 1},
                        'minItems': 1,
                    },
                ]
            },
            'phone': {'type': 'string'},
            'is-enabled': {'type': 'boolean'},
            'notifications-by-role': {
                'type': 'object',
                'additionalProperties': False,
                'minProperties': 1,
                'properties': {
                    'state': {'type': 'string', 'enum': ['On', 'Off']},
                    'roles': {
                        'type': 'array',
                        'items': {
                            'type': 'string',
                            'enum': ['AccountAdmin', 'ServiceAdmin', 'Owner', 'Contributor'],
                        },
                    },
                },
            },
            'notifications-sources': {
                'type': 'array',
                'minItems': 1,
                'items': {
                    'oneOf': [
                        {
                            'type': 'object',
                            'additionalProperties': False,
                            'required': ['source-type', 'minimal-severity'],
                            'properties': {
                                'source-type': {'enum': ['Alert']},
                                'minimal-severity': {
                                    'type': 'string',
                                    'enum': ['High', 'Medium', 'Low'],
                                },
                            },
                        },
                        {
                            'type': 'object',
                            'additionalProperties': False,
                            'required': ['source-type', 'minimal-risk-level'],
                            'properties': {
                                'source-type': {'enum': ['AttackPath']},
                                'minimal-risk-level': {
                                    'type': 'string',
                                    'enum': ['Critical', 'High', 'Medium', 'Low'],
                                },
                            },
                        },
                    ]
                },
            },
        }
    )

    settable = ('emails', 'phone', 'is-enabled', 'notifications-by-role', 'notifications-sources')

    log = logging.getLogger('custodian.azure.defender.SetSecurityContactAction')

    def validate(self):
        if not any(k in self.data for k in self.settable):
            raise PolicyValidationError(
                f"set-security-contact requires at least one of: {', '.join(self.settable)}"
            )
        return self

    def _process_resources(self, resources, event):
        # The base class logs and swallows errors outside pytest, so a failed write
        # would leave the run looking successful. Set the rest, then raise.
        self._prepare_processing()
        failures = []
        for resource in resources:
            try:
                self._log_modified_resource(resource, self._process_resource(resource))
            except Exception as e:
                self.log.error(
                    "Setting security contact '%s' failed: %s",
                    resource.get('name'), e,
                    exc_info=True, extra=self._get_action_log_metadata(resource))
                failures.append(e)
        if failures:
            raise failures[0]

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        contact = self.client.security_contacts.get(resource['name'])

        if 'emails' in self.data:
            emails = self.data['emails']
            contact.emails = emails if isinstance(emails, str) else ';'.join(emails)
        if 'phone' in self.data:
            contact.phone = self.data['phone']
        if 'is-enabled' in self.data:
            contact.is_enabled = self.data['is-enabled']
        if 'notifications-by-role' in self.data:
            by_role = self.data['notifications-by-role']
            current = (
                contact.notifications_by_role or SecurityContactPropertiesNotificationsByRole()
            )
            if 'state' in by_role:
                current.state = by_role['state']
            if 'roles' in by_role:
                current.roles = by_role['roles']
            contact.notifications_by_role = current
        if 'notifications-sources' in self.data:
            contact.notifications_sources = [
                self._build_source(s) for s in self.data['notifications-sources']
            ]

        self.client.security_contacts.create(resource['name'], contact)

    @staticmethod
    def _build_source(source):
        if source['source-type'] == 'Alert':
            return NotificationsSourceAlert(minimal_severity=source['minimal-severity'])
        return NotificationsSourceAttackPath(minimal_risk_level=source['minimal-risk-level'])


@resources.register("defender-jit-policy")
class DefenderJitPolicy(QueryResourceManager, metaclass=QueryMeta):
    class resource_type(TypeInfo):
        doc_groups = ["Security"]

        service = "azure.mgmt.security"
        client = "SecurityCenter"
        enum_spec = ("jit_network_access_policies", "list", None)
        resource_type = "Microsoft.Security/jitNetworkAccessPolicies"
        default_report_fields = ["id", "name"]
