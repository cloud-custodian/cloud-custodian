# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources


@resources.register('disk')
class Disk(ArmResourceManager):
    """Disk Resource

    :example:

    This policy will find all data disks that are not being managed by a VM.

    .. code-block:: yaml

        policies:
          - name: orphaned-disk
            resource: azure.disk
            filters:
              - type: value
                key: managedBy
                value: null

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Storage']

        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        enum_spec = ('disks', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.diskState',
            'sku.name'
        )
        resource_type = 'Microsoft.Compute/disks'

@Disk.action_registry.register('snapshot')
class DiskSnapshotAction(AzureBaseAction):

    schema = type_schema('snapshot')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.snapshots.create_or_update(resource['resourceGroup'], resource['name']+'_'+datetime.today().strftime('%Y-%m-%d'), resource)
