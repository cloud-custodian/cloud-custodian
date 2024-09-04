# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.mgmt.security import SecurityCenter

from c7n.utils import local_session
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager, QueryMeta, TypeInfo


class DefenderResourceManager(QueryResourceManager):
    """Manager for Microsoft Defender resources

    Note: The "Microsoft Defender for Cloud" name replaces and
    consolidates products previously called Azure Security Center
    and Azure Defender.

    The Azure Security SDK takes different arguments for its
    SecurityCenter client than other service SDKs use.

    We can override client creation here to help simplify individual
    Defender resource definitions.
    """

    def get_client(self):
        session = local_session(self.session_factory)

        # The SecurityCenter client takes an "asc_location" parameter, and the
        # documentation[^1] points out that this can come from the locations
        # list (elsewhere there are references to using a subscription's
        # "home region" for asc_location).
        #
        # However, from peeking at the Azure CLI's code it looks like they
        # hardcode an arbitrary/common location[^2]. The initial pull request
        # adding Defender to the CLI[^3] mentions that the intention is to
        # remove asc_location from client creation and hide it from the user.
        #
        # Following the Azure CLI team's lead and hardcoding "centralus"
        # here seems reasonable.
        #
        # [^1]: https://azuresdkdocs.blob.core.windows.net/$web/python/azure-mgmt-security/1.0.0/azure.mgmt.security.html#azure.mgmt.security.SecurityCenter  # noqa
        # [^2]: https://github.com/Azure/azure-cli/blob/29767d75d850ddc1c24cc85bd46d861b61d77a47/src/azure-cli/azure/cli/command_modules/security/_client_factory.py#L11  # noqa
        # [^3]: https://github.com/Azure/azure-cli/pull/7917#discussion_r238458818  # noqa
        return SecurityCenter(session.get_credentials(), session.subscription_id, "centralus")


@resources.register("defender-pricing")
class DefenderPricing(DefenderResourceManager, metaclass=QueryMeta):
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
        service = "security"
        resource_type = "Microsoft.Security/pricings"


@resources.register("defender-setting")
class DefenderSetting(DefenderResourceManager, metaclass=QueryMeta):
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
        service = "security"
        resource_type = "Microsoft.Security/settings"


@resources.register("defender-autoprovisioning")
class DefenderAutoProvisioningSetting(DefenderResourceManager, metaclass=QueryMeta):
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
        service = "security"
        resource_type = "Microsoft.Security/autoProvisioningSettings"


@resources.register("defender-alert")
class DefenderAlertSettings(DefenderResourceManager, metaclass=QueryMeta):
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
        service = "security"
        resource_type = "Microsoft.Security/alertNotifications"


@resources.register("defender-assessment")
class DefenderAssessment(DefenderResourceManager, metaclass=QueryMeta):
    class resource_type(TypeInfo):
        doc_groups = ["Security"]

        id = "id"
        name = "name"
        service = "security"
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
class DefenderSecurityContact(DefenderResourceManager, metaclass=QueryMeta):
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
        service = "security"
        client = "SecurityCenter"
        enum_spec = ("security_contacts", "list", None)
        resource_type = "Microsoft.Security/securityContacts"
        default_report_fields = ["id", "name"]


@resources.register("defender-jit-policy")
class DefenderJitPolicy(DefenderResourceManager, metaclass=QueryMeta):
    class resource_type(TypeInfo):
        doc_groups = ["Security"]

        service = "security"
        client = "SecurityCenter"
        enum_spec = ("jit_network_access_policies", "list", None)
        resource_type = "Microsoft.Security/jitNetworkAccessPolicies"
        default_report_fields = ["id", "name"]
