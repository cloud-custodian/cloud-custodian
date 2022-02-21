# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import jmespath
import requests
from azure.mgmt.security import SecurityCenter

from c7n.utils import local_session
from c7n_azure.constants import RESOURCE_GLOBAL_MGMT
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager, QueryMeta, TypeInfo


class SecurityResourceManager(QueryResourceManager):
    """Manager for Security Center resources

    The Azure Security SDK takes different arguments for its
    SecurityCenter client than other service SDKs use. Notably, it
    takes an `asc_location` which comes from the `locations` API.

    We can override client creation here to use a subscription's
    home region, which should help simplify individual Defender
    resource definitions.
    """

    def get_client(self):
        session = local_session(self.session_factory)
        credentials = session.get_credentials()
        token = credentials.get_token(RESOURCE_GLOBAL_MGMT + '.default')
        locations_path = f'/subscriptions/{session.subscription_id}/providers/Microsoft.Security/locations/'
        api_version = session.resource_api_version(locations_path)
        response = requests.get(
            f'{RESOURCE_GLOBAL_MGMT}/{locations_path}?api-version={api_version}',
            headers={'Authorization': f'Bearer {token.token}'})
        home_region = jmespath.search('value[].properties.homeRegionName|[0]', response.json())
        return SecurityCenter(credentials, session.subscription_id, home_region)


@resources.register('defender-pricing')
class DefenderPricing(SecurityResourceManager, metaclass=QueryMeta):
    """Active Azure Defender pricing details for supported resources.

    :example:

    Check if the Key Vaults resource is operating under the Standard
    pricing tier. This equates to Azure Defender being "On" in some
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
        doc_groups = ['Security']

        id = 'id'
        name = 'name'
        enum_spec = ('pricings', 'list', None)
        client = 'SecurityCenter'
        filter_name = None
        service = 'security'
        resource_type = 'Microsoft.Security/pricings'


@resources.register('defender-setting')
class DefenderSetting(SecurityResourceManager, metaclass=QueryMeta):
    """Top-level Azure Defender settings for a subscription.

    :example:

    Check that the MCAS integration with Azure Defender is enabled.

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
        doc_groups = ['Security']

        id = 'id'
        name = 'name'
        enum_spec = ('settings', 'list', None)
        client = 'SecurityCenter'
        filter_name = None
        service = 'security'
        resource_type = 'Microsoft.Security/settings'


@resources.register('defender-autoprovisioning')
class DefenderAutoProvisioningSetting(SecurityResourceManager, metaclass=QueryMeta):
    """Auto-provisioning settings for Azure Defender agents.

    :example:

    Check that auto-provisioning is enabled for the Azure Defender monitoring agent.

    .. code-block:: yaml

        policies:
          - name: azure-defender-auto-provisioning-enabled
            resource: azure.defender-autoprovisioning
            filters:
            - name: default
            - properties.autoProvision: "On"
    """

    class resource_type(TypeInfo):
        doc_groups = ['Security']

        id = 'id'
        name = 'name'
        enum_spec = ('auto_provisioning_settings', 'list', None)
        client = 'SecurityCenter'
        filter_name = None
        service = 'security'
        resource_type = 'Microsoft.Security/autoProvisioningSettings'
