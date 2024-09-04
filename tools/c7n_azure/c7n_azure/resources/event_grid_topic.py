from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager


@resources.register('event-grid-topic')
class EventGridTopic(QueryResourceManager):
    """Event Grid Topic Resource

    :example:

    Finds all Event Grid Topics in the subscription

    .. code-block:: yaml

        policies:
            - name: find-all-event-grid-topics
              resource: azure.event-grid-topic
    """

    class resource_type(QueryResourceManager.resource_type):
        doc_groups = ['Events']

        service = 'azure.mgmt.eventgrid'
        client = 'EventGridManagementClient'
        enum_spec = ('topics', 'list_by_subscription', None)
