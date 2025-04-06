# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n.filters import ListItemFilter
from c7n.utils import type_schema


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


@Disk.filter_registry.register("snapshots")
class DiskSnapshotsFilter(ListItemFilter):
    schema = type_schema(
        "snapshots",
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )
    annotate_items = True
    item_annotation_key = "c7n:Snapshots"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._snapshots = ()

    def process(self, resources, event=None):
        self._snapshots = tuple(
            item.serialize(True)
            for item in self.manager.get_client().snapshots.list()
        )
        return super().process(resources, event)

    def get_item_values(self, resource):
        uid = resource['properties']['uniqueId']
        filtered = []
        for item in self._snapshots:
            source_uid = item['properties'].get('creationData', {}).get('sourceUniqueId')
            if source_uid == uid:
                filtered.append(item)
        return filtered
