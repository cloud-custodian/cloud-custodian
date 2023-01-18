from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('activity-log-alert')
class ActivityLogAlert(ArmResourceManager):
    """Activity Log Alert Resource

        :example:

        .. code-block:: yaml

            policies:
              - name: azure-activity-log-alert
                resource: azure.activity-log-alert
                filters:
                  - type: value
                    key: properties.enabled
                    value: true
    """
    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Monitors']

        service = 'azure.mgmt.monitor'
        client = 'MonitorManagementClient'
        enum_spec = ('activity_log_alerts', 'list_by_subscription_id', None)
        resource_type = 'Microsoft.Insights/ActivityLogAlerts'
