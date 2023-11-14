from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('datalake-analytics')
class DataLakeAnalytics(ArmResourceManager):
    """Data Lake Analytics Resource

    :example:

    This policy will find all Datalake Analytics

    .. code-block:: yaml

        policies:
          - name: datalake-analytics
            resource: azure.datalake-analytics

    """
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Analytics']

        service = 'azure.mgmt.datalake.analytics'
        client = 'DataLakeAnalyticsAccountManagementClient'
        enum_spec = ('accounts', 'list', None)
        resource_type = 'Microsoft.DataLakeAnalytics/analytics'
