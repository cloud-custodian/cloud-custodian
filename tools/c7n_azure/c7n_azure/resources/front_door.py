# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources


@resources.register('front-door')
class FrontDoor(ArmResourceManager):
    """Azure Front Door Resource

    :example:

    This policy will find all Front Doors

    .. code-block:: yaml

        policies:
          - name: all-front-doors
            resource: azure.front-door
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Network']

        service = 'azure.mgmt.frontdoor'
        client = 'FrontDoorManagementClient'
        enum_spec = ('front_doors', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Network/frontDoors'
