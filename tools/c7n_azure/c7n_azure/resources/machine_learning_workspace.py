from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n.utils import type_schema
from c7n.filters import ListItemFilter
from c7n_azure.utils import ResourceIdParser
from azure.mgmt.machinelearningservices.models import (ComputeInstanceProperties,
                                                       AmlComputeProperties)


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
