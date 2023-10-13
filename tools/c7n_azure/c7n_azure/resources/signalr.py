from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('signalr')
class Signalr(ArmResourceManager):
    """Signalr Resource

    :example:

    Finds SignalR service without Private Endpoint connection configured

    .. code-block:: yaml

        policies:
          - name: asb_signalr_private_link
            resource: azure.signalr
            filters:
              - not:
                  - type: value
                    key: properties.privateEndpointConnections[].properties.privateLinkServiceConnectionState.status
                    value: Approved
                    op: contains

    """  # noqa
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Networking']
        service = 'azure.mgmt.signalr'
        client = 'SignalRManagementClient'
        enum_spec = ('signal_r', 'list_by_subscription', None)
        resource_type = 'Microsoft.SignalRService/signalR'
