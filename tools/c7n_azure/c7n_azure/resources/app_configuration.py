from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('app-configuration')
class AppConfiguration(ArmResourceManager):
    """App Configuration Resource

        :example:

        The policy finds App Configurations whose Private Endpoint Connections have Approved status

        .. code-block:: yaml

            policies:
              - name: azure-app-configuration
                resource: azure.app-configuration
                filters:
                  - type: value
                    key: properties.privateEndpointConnections[].properties.privateLinkServiceConnectionState.status
                    value: Approved
                    op: contains
    """
    class resource_type(ArmResourceManager.resource_type):

        service = 'azure.mgmt.appconfiguration'
        client = 'AppConfigurationManagementClient'
        enum_spec = ('configuration_stores', 'list', None)
        resource_type = 'Microsoft.AppConfiguration/configurationStores'
