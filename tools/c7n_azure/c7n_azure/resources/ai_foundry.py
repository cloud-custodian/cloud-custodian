# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import requests

from azure.mgmt.cognitiveservices.models import ConnectionPropertiesV2
from azure.mgmt.resource.resources.models import GenericResource
from msrestazure.tools import parse_resource_id

from c7n.utils import type_schema
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager


_MSREST_SCALARS = {
    'str': {'type': 'string'},
    'bool': {'type': 'boolean'},
    'int': {'type': 'integer'},
    'float': {'type': 'number'},
    'iso-8601': {'type': ['string', 'null']},
}


def _msrest_type_to_jsonschema(msrest_type):
    if msrest_type.startswith('[') and msrest_type.endswith(']'):
        return {
            'type': 'array',
            'items': _msrest_type_to_jsonschema(msrest_type[1:-1])
        }
    if msrest_type.startswith('{') and msrest_type.endswith('}'):
        return {
            'type': 'object',
            'additionalProperties': _msrest_type_to_jsonschema(msrest_type[1:-1])
        }
    return _MSREST_SCALARS.get(msrest_type, {'type': 'object'})


_READONLY_CONNECTION_PROPERTIES = {
    key for key, value in ConnectionPropertiesV2._validation.items()
    if value.get('readonly')
}


WRITABLE_PROPERTIES_SCHEMA = {
    info['key']: _msrest_type_to_jsonschema(info['type'])
    for snake, info in ConnectionPropertiesV2._attribute_map.items()
    if snake not in _READONLY_CONNECTION_PROPERTIES
}


@resources.register('cognitiveservice')
class CognitiveService(ArmResourceManager):
    """Cognitive Services Resource

    :example:

    This policy will find all Cognitive Service accounts with 1000 or more
    total errors over the 72 hours

    .. code-block:: yaml

        policies:
          - name: cogserv-many-failures
            resource: azure.cognitiveservice
            filters:
              - type: metric
                metric: TotalErrors
                op: ge
                aggregation: total
                threshold: 1000
                timeframe: 72
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        service = 'azure.mgmt.cognitiveservices'
        client = 'CognitiveServicesManagementClient'
        enum_spec = ('accounts', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name'
        )
        resource_type = 'Microsoft.CognitiveServices/accounts'


@resources.register('ai-foundry-project')
class AIFoundryProject(ChildArmResourceManager):
    """AI Foundry Project Resource

    :example:

    Find AI Foundry projects in a specific resource group.

    .. code-block:: yaml

        policies:
          - name: ai-foundry-projects-in-rg
            resource: azure.ai-foundry-project
            filters:
              - type: value
                key: resourceGroup
                op: eq
                value: my-ai-rg
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        service = 'azure.mgmt.cognitiveservices'
        client = 'CognitiveServicesManagementClient'
        enum_spec = ('projects', 'list', None)
        parent_manager_name = 'cognitiveservice'
        resource_type = 'Microsoft.CognitiveServices/accounts/projects'
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
                'account_name': parent_resource['name'],
            }


@resources.register('ai-foundry-connection')
class AIFoundryConnection(ChildArmResourceManager):
    """AI Foundry Project Connection Resource

    :example:

    Find AI Foundry project connections that are shared with all users.

    .. code-block:: yaml

        policies:
          - name: ai-foundry-shared-connections
            resource: azure.ai-foundry-connection
            filters:
              - type: value
                key: properties.isSharedToAll
                value: true
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        service = 'azure.mgmt.cognitiveservices'
        client = 'CognitiveServicesManagementClient'
        enum_spec = ('project_connections', 'list', None)
        parent_manager_name = 'ai-foundry-project'
        resource_type = 'Microsoft.CognitiveServices/accounts/projects/connections'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            '"c7n:parent-id"'
        )

        @classmethod
        def extra_args(cls, parent_resource):
            parsed = parse_resource_id(parent_resource['id'])
            return {
                'resource_group_name': parent_resource['resourceGroup'],
                'account_name': parsed['name'],
                'project_name': (
                    parsed.get('resource_name') or parsed.get('child_name_1')
                ),
            }


@AIFoundryConnection.action_registry.register('update')
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

    def _prepare_processing(self):
        self.client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')

    def _process_resource(self, resource):
        current_properties = resource.get('properties', {})
        desired_properties = dict(current_properties)
        desired_properties.update(self.data['properties'])

        # Keep the request minimal and include required discriminator fields.
        normalized = {
            key: desired_properties[key]
            for key in self.WRITABLE_PROPERTY_KEYS
            if key in desired_properties
        }

        api_version = self.session.resource_api_version(resource['id'])
        payload = GenericResource(properties=normalized)
        self.client.resources.begin_update_by_id(
            resource['id'], api_version, payload
        ).result()
        return "updated"


@resources.register('cognitiveservice-deployment')
class AiFoundryCognitiveServiceDeployment(ChildArmResourceManager):
    """AI Foundry deployment resource using Cognitive Services list API.

    Uses the Azure AI Services account-management surface
    (``Microsoft.CognitiveServices/accounts/deployments``) with API version
    ``2024-10-01``.

    :example:

    This policy will find failed or canceled AI Foundry model deployments.

    .. code-block:: yaml

        policies:
          - name: cognitiveservice-deployments-find-failed
            resource: azure.cognitiveservice-deployment
            filters:
              - type: value
                key: properties.provisioningState
                op: in
                value: [Failed, Canceled]
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        api_version = '2024-10-01'
        service = 'azure.mgmt.cognitiveservices'
        client = 'CognitiveServicesManagementClient'
        enum_spec = ('deployments', 'list', None)
        parent_manager_name = 'cognitiveservice'
        resource_type = 'Microsoft.CognitiveServices/accounts/deployments'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'type'
        )

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': parent_resource['resourceGroup'],
                'account_name': parent_resource['name'],
            }

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
        session = self.get_session()
        scope = f'{session.resource_endpoint}.default'
        token = session.credentials.get_token(scope)
        url = (
            f'{session.cloud_endpoints.endpoints.resource_manager}'
            f'{parent_resource["id"]}/deployments'
        )
        response = requests.get(
            url,
            headers={'Authorization': f'Bearer {token.token}'},
            params={'api-version': type_info.api_version},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        if 'value' not in payload:
            raise TypeError(
                'Enumerating AI Foundry deployments returned a payload without a value list.'
            )

        return payload['value']


@resources.register('ai-foundry-application')
class AIFoundryApplication(ChildArmResourceManager):
    """Azure AI Foundry Application Resource."""

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        api_version = '2025-10-01-preview'
        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        parent_manager_name = 'ai-foundry-project'
        resource_type = 'Microsoft.CognitiveServices/accounts/projects/applications'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            '"c7n:parent-id"'
        )

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
        management_endpoint = self.get_session().cloud_endpoints.endpoints.resource_manager
        url = (
            f"{management_endpoint}{parent_resource['id'].lstrip('/')}"
            "/applications"
        )
        return self._arm_rest_get(
            url,
            params={'api-version': self.resource_type.api_version},
            timeout=30,
            max_retries=3
        )


@resources.register('ai-foundry-agent')
class AIFoundryAgent(ChildArmResourceManager):
    """Azure AI Foundry Application Agent Reference Resource."""

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        api_version = '2025-10-01-preview'
        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        enum_spec = ('resources', 'list', None)
        parent_manager_name = 'ai-foundry-application'
        resource_type = 'Microsoft.CognitiveServices/accounts/projects/applications/agents'
        default_report_fields = (
            'name',
            'id',
            '"c7n:parent-id"'
        )

    @staticmethod
    def _is_agent_of_parent(resource, parent_id):
        parent_prefix = "{}/agents/".format(parent_id.rstrip('/').lower())
        return resource.get('id', '').lower().startswith(parent_prefix)

    @staticmethod
    def _normalize_agent_reference(parent_resource, agent):
        agent_name = agent.get('agentName')
        service_agent_id = agent.get('agentId')
        arm_child_id = "{}/agents/{}".format(parent_resource['id'].rstrip('/'), agent_name)

        normalized = {
            'id': arm_child_id,
            'name': agent_name,
            'type': 'Microsoft.CognitiveServices/accounts/projects/applications/agents',
            'resourceGroup': parent_resource.get('resourceGroup'),
            'properties': {
                'agentId': service_agent_id,
                'agentName': agent_name
            },
            'applicationAgentRef': dict(agent)
        }
        return normalized

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
        app_agents = parent_resource.get('properties', {}).get('agents', [])
        if not app_agents:
            return []

        normalized = [self._normalize_agent_reference(parent_resource, v) for v in app_agents]
        return [r for r in normalized if self._is_agent_of_parent(r, parent_resource['id'])]


class AiFoundryCognitiveServiceDeploymentDeleteAction(AzureBaseAction):
    """Delete AI Foundry Cognitive Services deployments."""

    schema = type_schema('delete')
    schema_alias = True

    def _prepare_processing(self):
        self.client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')

    def _process_resource(self, resource):
        self.client.resources.begin_delete_by_id(
            resource['id'],
            self.manager.resource_type.api_version,
        )
        return "deleted"


def register_ai_foundry_cognitive_service_deployment_actions(registry, resource_class):
    """Register explicit delete action for nested deployment resources."""
    if resource_class is AiFoundryCognitiveServiceDeployment:
        resource_class.action_registry.register(
            'delete',
            AiFoundryCognitiveServiceDeploymentDeleteAction,
        )


resources.subscribe(register_ai_foundry_cognitive_service_deployment_actions)


@resources.register('ai-foundry-deployment')
class AiFoundryDeployment(AiFoundryCognitiveServiceDeployment):
    """Azure AI Foundry Deployment Resource.

    Shares the same endpoint path as
    ``azure.cognitiveservice-deployment`` but uses the AI Foundry API version
    ``2025-06-01``.
    """

    class resource_type(AiFoundryCognitiveServiceDeployment.resource_type):
        api_version = '2025-06-01'


def register_ai_foundry_deployment_actions(registry, resource_class):
    """Register explicit delete action for nested deployment resources."""
    if resource_class is AiFoundryDeployment:
        resource_class.action_registry.register(
            'delete',
            AiFoundryCognitiveServiceDeploymentDeleteAction
        )


resources.subscribe(register_ai_foundry_deployment_actions)
