# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.mgmt.security.models import Extension
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager, QueryMeta, TypeInfo

from c7n.exceptions import PolicyValidationError
from c7n.utils import type_schema


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


@DefenderPricing.action_registry.register('set-pricing-tier')
class DefenderPricingSetTierAction(AzureBaseAction):
    """Set the pricing tier of a subscription-level Microsoft Defender plan.

    Setting ``pricing-tier: Standard`` turns the plan on and ``Free`` turns it
    off. ``sub-plan``, ``enforce`` and ``extensions`` are optional and only
    change when set. Each ``extensions`` entry uses Azure's API casing and
    updates the extension with that name, leaving the plan's other extensions
    alone. Azure doesn't allow a sub-plan or extensions on the ``Free`` tier,
    so setting ``Free`` clears them.

    Changing ``sub-plan`` keeps the plan's current extensions. If the new
    sub-plan doesn't support one of them, such as moving Defender for Servers
    from ``P2`` to ``P1``, Azure may reject the update, so list those
    extensions in ``extensions`` with ``isEnabled: false``.

    Azure replaces the whole pricing on update, so the action reads the
    current pricing first and writes it back with only the requested fields
    changed.

    The caller needs ``Microsoft.Security/pricings/write`` on the subscription.

    Azure doesn't document every plan name in one place. To see the plans a
    subscription has, with their tier, sub-plan and whether they're
    deprecated, run:

    .. code-block:: shell

        az security pricing list -o table --query \\
          "value[].{name:name, tier:pricingTier, subPlan:subPlan, deprecated:deprecated}"

    :example:

    Turn on Microsoft Defender for App Service if it isn't already on.

    .. code-block:: yaml

        policies:
          - name: azure-defender-app-services-enabled
            resource: azure.defender-pricing
            filters:
              - name: AppServices
              - type: value
                key: properties.pricingTier
                op: not-equal
                value: Standard
            actions:
              - type: set-pricing-tier
                pricing-tier: Standard

    Turn off Microsoft Defender for Containers if it's on.

    .. code-block:: yaml

        policies:
          - name: azure-defender-containers-disabled
            resource: azure.defender-pricing
            filters:
              - name: Containers
              - properties.pricingTier: Standard
            actions:
              - type: set-pricing-tier
                pricing-tier: Free
    """
    permissions = ('Microsoft.Security/pricings/write',)

    schema = type_schema(
        'set-pricing-tier',
        required=['pricing-tier'],
        **{
            'pricing-tier': {'type': 'string', 'enum': ['Free', 'Standard']},
            'sub-plan': {'type': 'string', 'minLength': 1},
            'enforce': {'type': 'boolean'},
            'extensions': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['name', 'isEnabled'],
                    'properties': {
                        'name': {'type': 'string', 'minLength': 1},
                        'isEnabled': {'type': 'boolean'},
                        'additionalExtensionProperties': {'type': 'object'},
                    },
                },
            },
        }
    )

    def validate(self):
        if self.data['pricing-tier'] == 'Free':
            for key in ('sub-plan', 'extensions'):
                if key in self.data:
                    raise PolicyValidationError(
                        f"{self.type}: {key} is not supported with pricing-tier 'Free'")
        return self

    def _process_resources(self, resources, event):
        # The base class logs and swallows errors outside pytest, so a failed
        # update would leave the run looking successful. Set the rest, then raise.
        self._prepare_processing()
        failures = []
        for resource in resources:
            try:
                self._log_modified_resource(resource, self._process_resource(resource))
            except Exception as e:
                self.log.error(
                    f"Setting pricing tier '{self.data['pricing-tier']}' on "
                    f"'{resource.get('name')}' failed: {e}",
                    exc_info=True, extra=self._get_action_log_metadata(resource))
                failures.append(e)
        if failures:
            raise failures[0]

    def _prepare_processing(self):
        self.client = self.manager.get_client()
        self.scope_id = f'subscriptions/{self.manager.get_session().get_subscription_id()}'

    def _process_resource(self, resource):
        pricing = self.client.pricings.get(self.scope_id, resource['name'])
        pricing.pricing_tier = self.data['pricing-tier']
        if pricing.pricing_tier == 'Free':
            # Azure rejects a sub-plan or extensions on the Free tier
            pricing.sub_plan = None
            pricing.extensions = None
        elif 'sub-plan' in self.data:
            pricing.sub_plan = self.data['sub-plan']
        # Azure takes "True"/"False" strings for these flags
        if 'enforce' in self.data:
            pricing.enforce = str(self.data['enforce'])
        if 'extensions' in self.data:
            extensions = {e.name: e for e in pricing.extensions or []}
            for ext in self.data['extensions']:
                current = extensions.setdefault(
                    ext['name'], Extension(name=ext['name'], is_enabled=None))
                current.is_enabled = str(ext['isEnabled'])
                if 'additionalExtensionProperties' in ext:
                    current.additional_extension_properties = ext['additionalExtensionProperties']
            pricing.extensions = list(extensions.values())

        self.client.pricings.update(self.scope_id, resource['name'], pricing)
        return f"Set pricing tier to '{self.data['pricing-tier']}'"


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


@resources.register("defender-jit-policy")
class DefenderJitPolicy(QueryResourceManager, metaclass=QueryMeta):
    class resource_type(TypeInfo):
        doc_groups = ["Security"]

        service = "azure.mgmt.security"
        client = "SecurityCenter"
        enum_spec = ("jit_network_access_policies", "list", None)
        resource_type = "Microsoft.Security/jitNetworkAccessPolicies"
        default_report_fields = ["id", "name"]
