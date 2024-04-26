from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager


@resources.register('event-grid-domain')
class EventGridDomain(QueryResourceManager):
    """Event Grid Domain Resource

    :example:

    Finds all Event Grid Domains in the subscription

    .. code-block:: yaml

        policies:
            - name: find-all-event-grid-domains
              resource: azure.event-grid-domain

    """

    class resource_type(QueryResourceManager.resource_type):
        doc_groups = ['Events']

        service = 'azure.mgmt.eventgrid'
        client = 'EventGridManagementClient'
        enum_spec = ('domains', 'list_by_subscription', None)
