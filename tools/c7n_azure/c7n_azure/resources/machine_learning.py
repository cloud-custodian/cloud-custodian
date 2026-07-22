from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager
from c7n.utils import type_schema
from c7n.filters import ListItemFilter
from c7n_azure.utils import ResourceIdParser
from azure.mgmt.machinelearningservices.models import (ComputeInstanceProperties,
                                                       AmlComputeProperties)


# Azure Machine Learning workspace resources
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


# Azure Machine Learning online endpoint resources
@resources.register('machine-learning-online-endpoint')
class MachineLearningOnlineEndpoint(ChildArmResourceManager):
    """Azure Machine Learning online endpoint resource.

    This resource enumerates online endpoints beneath every Machine Learning
    workspace. Use the ``online-deployments`` filter to select endpoints based
    on the deployments they contain.

    :example:

    Find succeeded endpoints with more than three served model versions.

    .. code-block:: yaml

        policies:
          - name: ml-endpoints-too-many-deployments
            resource: azure.machine-learning-online-endpoint
            filters:
              - properties.provisioningState: Succeeded
              - type: online-deployments
                attrs:
                  - type: value
                    key: properties.model
                    value: present
                count: 3
                count_op: gt
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['ML']
        service = 'azure.mgmt.machinelearningservices'
        client = 'MachineLearningServicesMgmtClient'
        enum_spec = ('online_endpoints', 'list', None)
        parent_manager_name = 'machine-learning-workspace'
        resource_type = 'Microsoft.MachineLearningServices/workspaces/onlineEndpoints'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            '"c7n:parent-id"',
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': ResourceIdParser.get_resource_group(parent_resource['id']),
                'workspace_name': parent_resource['name'],
            }


@MachineLearningOnlineEndpoint.filter_registry.register('online-deployments')
class OnlineDeploymentsFilter(ListItemFilter):
    """Filter online endpoints by their child deployments."""

    schema = type_schema(
        'online-deployments',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'},
    )
    annotate_items = True
    item_annotation_key = 'c7n:OnlineDeployments'

    def get_item_values(self, resource):
        deployments = self.manager.get_client().online_deployments.list(
            resource_group_name=ResourceIdParser.get_resource_group(resource['id']),
            workspace_name=resource['c7n:parent-id'].rstrip('/').rsplit('/', 1)[-1],
            endpoint_name=resource['name'],
        )
        return [deployment.serialize(True) for deployment in deployments]


# Azure Machine Learning online deployment resources
@resources.register('machine-learning-online-deployment')
class MachineLearningOnlineDeployment(ChildArmResourceManager):
    """Azure Machine Learning online deployment resource.

    Deployments are enumerated beneath every online endpoint and include the
    deployment's ``properties.model`` reference.

    :example:

    Find deployments whose model is not approved.

    .. code-block:: yaml

        policies:
          - name: ml-online-deployments-for-approved-models
            resource: azure.machine-learning-online-deployment
            filters:
              - type: value
                key: properties.model
                op: not-in
                value:
                  - azureml:model-a:12
                  - azureml:model-b:4
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['ML']
        service = 'azure.mgmt.machinelearningservices'
        client = 'MachineLearningServicesMgmtClient'
        enum_spec = ('online_deployments', 'list', None)
        parent_manager_name = 'machine-learning-online-endpoint'
        resource_type = (
            'Microsoft.MachineLearningServices/workspaces/onlineEndpoints/deployments'
        )
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            '"c7n:parent-id"',
            'properties.model',
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': ResourceIdParser.get_resource_group(parent_resource['id']),
                'workspace_name': parent_resource['c7n:parent-id'].rstrip('/').rsplit('/', 1)[-1],
                'endpoint_name': parent_resource['name'],
            }
