import logging

from azure.core.exceptions import ResourceNotFoundError
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager
from c7n.utils import type_schema
from c7n.filters import ListItemFilter
from c7n_azure.utils import ResourceIdParser
from azure.mgmt.machinelearningservices.models import (ComputeInstanceProperties,
                                                       AmlComputeProperties)

log = logging.getLogger('custodian.azure.machine_learning')


class MachineLearningWorkspaceChildMixin:
    """Skip workspaces that cannot have their children enumerated.

    ``workspaces.list_by_subscription`` keeps returning soft-deleted
    workspaces (``provisioningState: Deleting``) after their resource group
    is gone, and every child request against them fails. Skip those
    workspaces, and any other workspace that disappears mid-run, rather than
    failing the whole policy.

    Subclasses that need custom enumeration override
    ``enumerate_workspace_children`` instead of ``enumerate_resources``.
    """

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
        if parent_resource.get('properties', {}).get('provisioningState') == 'Deleting':
            log.warning('Skipping Machine Learning workspace %s: workspace is being deleted',
                        parent_resource['id'])
            return []
        try:
            return self.enumerate_workspace_children(
                parent_resource, type_info, vault_url=vault_url, **params)
        except ResourceNotFoundError as e:
            log.warning('Skipping Machine Learning workspace %s: %s', parent_resource['id'], e)
            return []

    def enumerate_workspace_children(self, parent_resource, type_info, vault_url=None, **params):
        return super().enumerate_resources(
            parent_resource, type_info, vault_url=vault_url, **params)


@resources.register('machine-learning-workspace')
class MachineLearningWorkspace(ArmResourceManager):
    """Machine Learning Workspace Resource

    :example:

    Finds all Machine Learning Workspaces in the subscription

    .. code-block:: yaml

        policies:
            - name: find-all-machine-learning-workspaces
              resource: azure.machine-learning-workspace

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['ML']

        service = 'azure.mgmt.machinelearningservices'
        client = 'MachineLearningServicesMgmtClient'
        enum_spec = ('workspaces', 'list_by_subscription', None)
        resource_type = 'Microsoft.MachineLearningServices/workspaces'


@MachineLearningWorkspace.filter_registry.register("compute-instances")
class ComputeInstancesFilter(ListItemFilter):
    schema = type_schema(
        "compute-instances",
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )
    annotate_items = True
    item_annotation_key = "c7n:ComputeInstances"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ComputeInstanceProperties.enable_additional_properties_sending()
        AmlComputeProperties.enable_additional_properties_sending()

    def get_item_values(self, resource):
        computes = self.manager.get_client().compute.list(
            resource_group_name=ResourceIdParser.get_resource_group(resource['id']),
            workspace_name=resource['name']
        )
        return [c.serialize(True) for c in computes]


@resources.register('machine-learning-data-container')
class MachineLearningDataContainer(MachineLearningWorkspaceChildMixin, ChildArmResourceManager):
    """Machine Learning Data Container Resource

    :example:

    Finds non-archived Machine Learning data containers.

    .. code-block:: yaml

        policies:
            - name: find-active-machine-learning-data-containers-older-than-90-days
              resource: azure.machine-learning-data-container
              filters:
                - type: value
                  key: properties.isArchived
                  value: false
                - type: value
                  key: systemData.lastModifiedAt
                  value_type: age
                  op: gt
                  value: 90

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['ML']

        service = 'azure.mgmt.machinelearningservices'
        client = 'MachineLearningServicesMgmtClient'
        enum_spec = ('data_containers', 'list', None)
        parent_manager_name = 'machine-learning-workspace'
        resource_type = 'Microsoft.MachineLearningServices/workspaces/data'
        default_report_fields = (
            'name',
            'resourceGroup',
            '"c7n:parent-id"',
            'properties.isArchived',
            'systemData.lastModifiedAt'
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': parent_resource['resourceGroup'],
                'workspace_name': parent_resource['name'],
                'list_view_type': 'All',
            }

    def augment(self, resources):
        for resource in resources:
            if 'id' in resource:
                resource['resourceGroup'] = ResourceIdParser.get_resource_group(resource['id'])
        return resources


@MachineLearningDataContainer.action_registry.register('archive')
class MachineLearningDataContainerArchiveAction(AzureBaseAction):
    """Archive Machine Learning data containers.

    Archiving hides the container and its versions from the workspace's
    active views. It does not delete the backing data.

    :example:

    .. code-block:: yaml

        policies:
            - name: archive-stale-machine-learning-data-containers
              resource: azure.machine-learning-data-container
              filters:
                - type: value
                  key: systemData.lastModifiedAt
                  value_type: age
                  op: gt
                  value: 90
              actions:
                - type: archive

    """

    schema = type_schema('archive')

    def _prepare_processing(self):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        if resource['properties']['isArchived']:
            return

        resource['properties']['isArchived'] = True
        self.client.data_containers.create_or_update(
            resource_group_name=resource['resourceGroup'],
            workspace_name=ResourceIdParser.get_resource_name(
                resource['c7n:parent-id']),
            name=resource['name'],
            body=resource,
            )
