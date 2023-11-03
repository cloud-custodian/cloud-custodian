from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('app-configuration')
class AppConfiguration(ArmResourceManager):
    """App Configuration Resource

    :example:

    The policy finds App Configurations whose Provisioned State is Succeeded

    .. code-block:: yaml

        policies:
          - name: azure-app-configuration
            resource: azure.app-configuration
            filters:
              - type: value
                key: properties.provisioningState
                value: Succeeded
                op: eq

    """
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Integration']

        service = 'azure.mgmt.appconfiguration'
        client = 'AppConfigurationManagementClient'
        enum_spec = ('configuration_stores', 'list', None)
        resource_type = 'Microsoft.AppConfiguration/configurationStores'
