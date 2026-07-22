from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager
from c7n.utils import type_schema
from c7n.filters import ListItemFilter
from c7n_azure.utils import ResourceIdParser
from azure.mgmt.machinelearningservices.models import (ComputeInstanceProperties,
                                                       AmlComputeProperties)


# Machine Learning Workspace
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


# Machine Learning Data Container
@resources.register('machine-learning-data-container')
class MachineLearningDataContainer(ChildArmResourceManager):
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
                  op: lt
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
                'workspace_name': parent_resource['name']
            }

    def augment(self, resources):
        for resource in resources:
            if 'id' in resource:
                resource['resourceGroup'] = ResourceIdParser.get_resource_group(resource['id'])
        return resources
