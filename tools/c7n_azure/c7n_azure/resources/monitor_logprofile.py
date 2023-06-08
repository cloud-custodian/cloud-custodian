# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('monitor-log-profile')
class MonitorLogprofile(ArmResourceManager):
    """Azure Monitor Log Profile Resource

    :example:

    Returns Monitor Log Profile resources

    .. code-block:: yaml

         policies:
          - name: basic-monitor-log-profile
            resource: azure.monitor-log-profile
            filters:
              - type: value
                key: categories
                op: in
                value: ["Delete"]

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Monitoring']

        service = 'azure.mgmt.monitor'
        client = 'MonitorManagementClient'
        enum_spec = ('log_profiles', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Insights/logprofiles'
