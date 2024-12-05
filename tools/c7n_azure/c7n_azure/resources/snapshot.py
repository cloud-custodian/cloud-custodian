# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n.utils import type_schema


@resources.register("snapshot")
class Snapshot(ArmResourceManager):
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
        doc_groups = ["Storage"]

        service = "azure.mgmt.compute"
        client = "ComputeManagementClient"
        enum_spec = ("snapshots", "list", None)
        default_report_fields = (
            "name",
            "location",
            "resourceGroup",
            "properties.diskState",
            "sku.name",
        )
        resource_type = "Microsoft.Compute/snapshots"


@Snapshot.action_registry.register("delete")
class DeleteSnapshot(AzureBaseAction):
    schema = type_schema("delete")

    def process(self, resources):
        return super().process(resources)

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        return self.client.snapshots.delete(
            resource["resourceGroup"],
            resource["name"],
        )
