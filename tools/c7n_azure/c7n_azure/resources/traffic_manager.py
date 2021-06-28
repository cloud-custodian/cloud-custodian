# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources


@resources.register('traffic-manager-profile')
class TrafficManagerProfile(ArmResourceManager):
    """Azure Traffic Manager Resource

    :example:

    This policy will find all Azure Traffic Manager profiles

    .. code-block:: yaml

        policies:
          - name: traffic-manager-profiles
            resource: azure.traffic-manager-profile

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Network']

        service = 'azure.mgmt.trafficmanager'
        client = 'TrafficManagerManagementClient'
        enum_spec = ('profiles', 'list_by_subscription', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Network/trafficmanagerprofiles'
