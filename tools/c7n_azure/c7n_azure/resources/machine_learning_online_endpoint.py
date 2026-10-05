# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.filters import ListItemFilter
from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.utils import ResourceIdParser


@resources.register('machine-learning-online-endpoint')
class MachineLearningOnlineEndpoint(ChildArmResourceManager):
    """Azure Machine Learning Online Endpoint Resource

    Online endpoints are child resources of a Machine Learning workspace
    (``Microsoft.MachineLearningServices/workspaces/onlineEndpoints``). They are
    enumerated per workspace using the ``OnlineEndpoints_List`` API.

    :example:

    Find Machine Learning online endpoints that are not in a succeeded
    provisioning state.

    .. code-block:: yaml

        policies:
          - name: ml-online-endpoints-not-succeeded
            resource: azure.machine-learning-online-endpoint
            filters:
              - type: value
                key: properties.provisioningState
                op: ne
                value: Succeeded

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        service = 'azure.mgmt.machinelearningservices'
        client = 'MachineLearningServicesMgmtClient'
        enum_spec = ('online_endpoints', 'list', None)
        parent_manager_name = 'machine-learning-workspace'
        resource_type = 'Microsoft.MachineLearningServices/workspaces/onlineEndpoints'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            '"c7n:parent-id"'
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': parent_resource['resourceGroup'],
                'workspace_name': parent_resource['name'],
            }


@MachineLearningOnlineEndpoint.filter_registry.register('online-deployments')
class OnlineDeploymentsFilter(ListItemFilter):
    """Filter online endpoints by their child deployments.

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
