# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.utils import ResourceIdParser


@resources.register('machine-learning-model-version')
class MachineLearningModelVersion(ChildArmResourceManager):
    """Machine Learning Model Version Resource

    Enumerates every model version registered in each Machine Learning
    workspace, allowing policies to find stale or unused model artifacts.

    :example:

    Find model versions that are not archived.

    .. code-block:: yaml

        policies:
          - name: ml-model-versions-active
            resource: azure.machine-learning-model-version
            filters:
              - type: value
                key: properties.isArchived
                value: false
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['ML']

        service = 'azure.mgmt.machinelearningservices'
        client = 'MachineLearningServicesMgmtClient'
        enum_spec = ('model_versions', 'list', None)
        parent_manager_name = 'machine-learning-workspace'
        resource_type = 'Microsoft.MachineLearningServices/workspaces/models/versions'
        default_report_fields = (
            'name',
            'resourceGroup',
            '"c7n:parent-id"'
        )

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
        client = self.get_client()
        resource_group = ResourceIdParser.get_resource_group(parent_resource['id'])
        workspace_name = parent_resource['name']

        versions = []
        for container in client.model_containers.list(
                resource_group_name=resource_group, workspace_name=workspace_name):
            for version in client.model_versions.list(
                    resource_group_name=resource_group,
                    workspace_name=workspace_name,
                    name=container.name):
                versions.append(version.serialize(True))
        return versions
