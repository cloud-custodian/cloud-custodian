from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources


@resources.register('stream-job')
class StreamJob(ArmResourceManager):
    """Azure Streaming Jobs Resource

    :example:

    This policy will lists the Streaming Jobs within an Azure subscription

    .. code-block:: yaml

        policies:
          - name: stream-job
            resource: azure.stream-job
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Network']

        service = 'azure.mgmt.streamanalytics'
        client = 'StreamAnalyticsManagementClient'
        enum_spec = ('streaming_jobs', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.StreamAnalytics/streamingjobs'
