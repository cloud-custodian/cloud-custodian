# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.core.exceptions import ResourceNotFoundError
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.utils import ResourceIdParser


@resources.register('machine-learning-environment-version')
class MachineLearningEnvironmentVersion(ChildArmResourceManager):
    """Machine Learning Environment Version Resource

    Enumerates every environment version in each Machine Learning
    workspace, including archived versions and versions of archived
    environments.

    ``properties.isArchived`` is only true for a version archived on its
    own. Archiving a whole environment does not set it on its versions.

    :example:

    Find user-created environment versions that are archived and older
    than 30 days.

    .. code-block:: yaml

        policies:
          - name: azure-ml-stale-archived-environment-versions
            resource: azure.machine-learning-environment-version
            filters:
              - type: value
                key: properties.environmentType
                value: UserCreated
              - type: value
                key: properties.isArchived
                value: true
              - type: value
                key: systemData.createdAt
                op: gt
                value_type: age
                value: 30
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['ML']

        service = 'azure.mgmt.machinelearningservices'
        client = 'MachineLearningServicesMgmtClient'
        enum_spec = ('environment_versions', 'list', None)
        parent_manager_name = 'machine-learning-workspace'
        resource_type = 'Microsoft.MachineLearningServices/workspaces/environments/versions'
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
        try:
            for container in client.environment_containers.list(
                    resource_group_name=resource_group,
                    workspace_name=workspace_name,
                    list_view_type="All"):
                try:
                    for version in client.environment_versions.list(
                            resource_group_name=resource_group,
                            workspace_name=workspace_name,
                            name=container.name,
                            list_view_type="All"):
                        versions.append(version.serialize(True))
                except ResourceNotFoundError:
                    # Curated environments are listed, but their versions live in a
                    # Microsoft registry.
                    continue
        except ResourceNotFoundError:
            # A workspace stuck deleting is still listed after its resource group is gone.
            return []
        return versions
