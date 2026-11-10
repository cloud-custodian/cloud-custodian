# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from azure.mgmt.core.tools import parse_resource_id
from azure.mgmt.machinelearningservices import models

from c7n.exceptions import PolicyExecutionError
from c7n.utils import type_schema
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.resources.machine_learning import MachineLearningWorkspaceChildMixin
from c7n_azure.utils import ResourceIdParser


@resources.register('machine-learning-model-version')
class MachineLearningModelVersion(MachineLearningWorkspaceChildMixin, ChildArmResourceManager):
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

    def enumerate_workspace_children(self, parent_resource, type_info, vault_url=None, **params):
        client = self.get_client()
        resource_group = ResourceIdParser.get_resource_group(parent_resource['id'])
        workspace_name = parent_resource['name']

        versions = []
        for container in client.model_containers.list(
                resource_group_name=resource_group, workspace_name=workspace_name):
            for version in client.model_versions.list(
                    resource_group_name=resource_group,
                    workspace_name=workspace_name,
                    name=container.name,
                    list_view_type="All"):
                versions.append(version.serialize(True))
        return versions


@MachineLearningModelVersion.action_registry.register('update')
class UpdateModelVersion(AzureBaseAction):
    """Update a model version's description, tags, stage, or archive state.

    Tags are replaced. Custom ``properties`` are added to existing properties;
    changing an existing value raises an error. When ``isArchived`` is set to
    ``true``, Azure also sets ``stage`` to ``Archived``.

    :example:

    Archive non-anonymous model versions that are not already archived.

    .. code-block:: yaml

        policies:
          - name: archive-named-model-versions
            resource: azure.machine-learning-model-version
            filters:
              - properties.isAnonymous: false
              - properties.isArchived: false
            actions:
              - type: update
                properties:
                  isArchived: true
    """

    schema = type_schema(
        'update',
        required=['properties'],
        properties={
            'type': 'object',
            'minProperties': 1,
            'additionalProperties': False,
            'properties': {
                'description': {'type': 'string'},
                'tags': {'type': 'object', 'additionalProperties': {'type': 'string'}},
                'properties': {'type': 'object', 'additionalProperties': {'type': 'string'}},
                'isArchived': {'type': 'boolean'},
                'stage': {'type': 'string'},
            },
        },
    )

    def _prepare_processing(self) -> None:
        self.client = self.manager.get_client()

    def _process_resource(self, resource: dict) -> str:
        resource_id = parse_resource_id(resource['id'])
        arguments = {
            'resource_group_name': resource_id['resource_group'],
            'workspace_name': resource_id['name'],
            'name': resource_id['child_name_1'],
            'version': resource_id['child_name_2'],
        }
        current = self.client.model_versions.get(**arguments)
        properties = current.properties.serialize()
        updates = self.data['properties'].copy()

        # The nested properties.properties dictionary holds custom string metadata,
        # not model fields such as isArchived. Azure accepts new metadata keys but
        # silently ignores changes to existing values, so reject those explicitly.
        if 'properties' in updates:
            existing = current.properties.properties or {}
            for key, value in updates['properties'].items():
                if key in existing and existing[key] != value:
                    raise PolicyExecutionError(
                        f'Cannot change existing model version property: {key}',
                    )
            # Preserve existing keys: Azure rejects attempts to remove them.
            updates['properties'] = {**existing, **updates['properties']}

        properties.update(updates)
        current.properties = models.ModelVersionProperties.deserialize(properties)
        self.client.model_versions.create_or_update(**arguments, body=current)
        return 'updated'
