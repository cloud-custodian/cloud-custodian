# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('bastion-host')
class AzureBastionHost(ArmResourceManager):
    """Bastion Host Resource

    :example:

    This policy will check if Bastion Host exists.

    .. code-block:: yaml

        policies:
          - name: check-bastion-host
            resource: azure.bastion-host
            filters:
              - type: value
                key: name
                value: present

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('bastion_hosts', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Network/bastionHosts'
