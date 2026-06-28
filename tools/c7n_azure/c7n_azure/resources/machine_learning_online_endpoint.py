# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager


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
