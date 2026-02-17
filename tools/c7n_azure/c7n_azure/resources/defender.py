# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

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


@resources.register("defender-jit-policy")
class DefenderJitPolicy(QueryResourceManager, metaclass=QueryMeta):
    class resource_type(TypeInfo):
        doc_groups = ["Security"]

        service = "azure.mgmt.security"
        client = "SecurityCenter"
        enum_spec = ("jit_network_access_policies", "list", None)
        resource_type = "Microsoft.Security/jitNetworkAccessPolicies"
        default_report_fields = ["id", "name"]
