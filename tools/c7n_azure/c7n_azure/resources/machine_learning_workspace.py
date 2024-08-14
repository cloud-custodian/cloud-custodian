from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager
from c7n.utils import type_schema
from c7n.filters import ListItemFilter
from c7n_azure.utils import ResourceIdParser


@resources.register('machine-learning-workspace')
class MachineLearningWorkspace(QueryResourceManager):
    """Machine Learning Workspace Resource

    :example:

    Finds all Machine Learning Workspaces in the subscription

    .. code-block:: yaml

        policies:
            - name: find-all-machine-learning-workspaces
              resource: azure.machine-learning-workspace

    """

    class resource_type(QueryResourceManager.resource_type):
        doc_groups = ['ML']

        service = 'azure.mgmt.machinelearningservices'
        client = 'AzureMachineLearningWorkspaces'
        enum_spec = ('workspaces', 'list_by_subscription', None)


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

    def get_item_values(self, resource):
        computes = self.manager.get_client().machine_learning_compute.list_by_workspace(
            resource_group_name=ResourceIdParser.get_resource_group(resource['id']),
            workspace_name=resource['name']
        )
        return [c.serialize(True) for c in computes]
