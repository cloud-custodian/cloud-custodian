# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.utils import ResourceIdParser
from c7n.utils import type_schema
from msrestazure.tools import parse_resource_id


WRITABLE_PROPERTIES_SCHEMA = {
    'authType': {'type': 'string'},
    'category': {'type': 'string'},
    'target': {'type': 'string'},
    'metadata': {'type': 'object'},
    'isSharedToAll': {'type': 'boolean'},
    'group': {'type': 'string'},
    'expiryTime': {'type': ['string', 'null']},
    'useWorkspaceManagedIdentity': {'type': 'boolean'},
    'sharedUserList': {'type': 'array'},
}


def _get_account_name_from_project(project_resource):
    account_id = project_resource.get('c7n:parent-id')
    return ResourceIdParser.get_resource_name(account_id)


def _get_project_name_from_project(project_resource):
    return _extract_account_and_project_from_parent_id(project_resource.get('id', ''))[1]


def _extract_account_and_project_from_parent_id(parent_id):
    parsed = parse_resource_id(parent_id) if parent_id else {}
    account_name = parsed.get('name')
    project_name = (
        parsed.get('resource_name') or
        parsed.get('child_name_1')
    )
    return account_name, project_name


def _extract_connection_resource_names(resource):
    resource_id = resource['id']
    parsed = parse_resource_id(resource_id)

    return {
        'resource_group_name': resource.get('resourceGroup') or
        ResourceIdParser.get_resource_group(resource_id),
        'account_name': parsed.get('name'),
        'project_name': parsed.get('child_name_1'),
        'connection_name': (parsed.get('resource_name'))
    }


@resources.register('ai-foundry-connection')
class AIFoundryConnection(ChildArmResourceManager):
    """Azure AI Foundry Project Connection Resource."""

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        api_version = '2025-06-01'
        service = 'azure.mgmt.cognitiveservices'
        client = 'CognitiveServicesManagementClient'
        enum_spec = (
            'project_connections',
            'list',
            {
                'resource_group_name': lambda parent: parent['resourceGroup'],
                'account_name': lambda parent: _get_account_name_from_project(parent),
                'project_name': lambda parent: _get_project_name_from_project(parent),
                'include_all': lambda parent: True
            }
        )
        parent_manager_name = 'ai-foundry-project'
        resource_type = 'Microsoft.CognitiveServices/accounts/projects/connections'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            '"c7n:parent-id"'
        )


class AIFoundryConnectionUpdateAction(AzureBaseAction):
    """Update an Azure AI Foundry project connection using ARM PATCH."""

    WRITABLE_PROPERTY_KEYS = tuple(WRITABLE_PROPERTIES_SCHEMA.keys())
    schema = type_schema(
        'update',
        required=['properties'],
        properties={
            'type': 'object',
            'additionalProperties': False,
            'properties': WRITABLE_PROPERTIES_SCHEMA
        }
    )
    schema_alias = True

    @staticmethod
    def _get_resource_names(resource):
        return _extract_connection_resource_names(resource)

    def _process_resource(self, resource):
        self.client = self.manager.get_client(
            'azure.mgmt.cognitiveservices.CognitiveServicesManagementClient'
        )
        names = self._get_resource_names(resource)

        current_properties = resource.get('properties', {})
        desired_properties = dict(current_properties)
        desired_properties.update(self.data['properties'])

        # Keep the request minimal and include required discriminator fields.
        normalized = {
            key: desired_properties[key]
            for key in self.WRITABLE_PROPERTY_KEYS
            if key in desired_properties
        }

        payload = {'properties': normalized}
        self.client.project_connections.update(
            resource_group_name=names['resource_group_name'],
            account_name=names['account_name'],
            project_name=names['project_name'],
            connection_name=names['connection_name'],
            connection=payload
        )
        return "updated"


def register_ai_foundry_connection_actions(registry, resource_class):
    if resource_class is AIFoundryConnection:
        resource_class.action_registry.register('update', AIFoundryConnectionUpdateAction)


resources.subscribe(register_ai_foundry_connection_actions)


@resources.register('ai-foundry-project')
class AIFoundryProject(ChildArmResourceManager):
    """Azure AI Foundry Project Resource."""

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        enum_spec = (
            'resources',
            'list_by_resource_group',
            {
                'resource_group_name': lambda parent: parent['resourceGroup'],
                'filter': lambda parent: (
                    "resourceType eq 'Microsoft.CognitiveServices/accounts/projects'"
                )
            }
        )
        parent_manager_name = 'cognitiveservice'
        resource_type = 'Microsoft.CognitiveServices/accounts/projects'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            '"c7n:parent-id"'
        )

    @staticmethod
    def _is_project_of_parent(resource, parent_id):
        resource_id = resource.get('id')
        if not resource_id or not parent_id:
            return False

        parent_parsed = parse_resource_id(parent_id)
        child_parsed = parse_resource_id(resource_id)

        return (
            (parent_parsed.get('subscription') or '').lower() ==
            (child_parsed.get('subscription') or '').lower() and
            (parent_parsed.get('resource_group') or '').lower() ==
            (child_parsed.get('resource_group') or '').lower() and
            (parent_parsed.get('name') or '').lower() ==
            (child_parsed.get('name') or '').lower() and
            (child_parsed.get('type') or '').lower() == 'accounts' and
            (child_parsed.get('child_type_1') or '').lower() == 'projects'
        )

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
        resources = super().enumerate_resources(parent_resource, type_info, vault_url, **params)
        parent_id = parent_resource['id']
        return [r for r in resources if self._is_project_of_parent(r, parent_id)]
