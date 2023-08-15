# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('alert-logs')
class AlertLogs(ArmResourceManager):
    """Azure Monitor Resource

    :example:

    Returns all azure alert Logs settings

    .. code-block:: yaml

        policies:
        - name: list-advisor-security-recommendations
          resource: azure.alert-logs
          filters:
            - type: value
              key: location
              value: "Global"
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Alerts Management']

        service = 'azure.mgmt.monitor'
        client = 'MonitorManagementClient'
        enum_spec = ('activity_log_alerts', 'list_by_subscription_id', None)
        default_report_fields = (
            'name',
            'resourceGroup',
            'properties.scopes',
            'properties.condition',
            'properties.actions'
        )
        resource_type = 'Microsoft.Insights/ActivityLogAlerts'
