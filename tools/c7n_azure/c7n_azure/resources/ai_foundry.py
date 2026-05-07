# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager
from c7n_azure.actions.base import AzureBaseAction
from c7n.utils import type_schema


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


@resources.register('ai-foundry-cognitiveservice-deployment')
class AiFoundryCognitiveServiceDeployment(ChildArmResourceManager):
    """AI Foundry deployment resource using Cognitive Services list API.

    Uses the Azure AI Services account-management surface
    (``Microsoft.CognitiveServices/accounts/deployments``) with API version
    ``2024-10-01``.

    :example:

    This policy will find failed or canceled AI Foundry model deployments.

    .. code-block:: yaml

        policies:
          - name: ai-foundry-cognitiveservice-deployments-find-failed
            resource: azure.ai-foundry-cognitiveservice-deployment
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


class AiFoundryCognitiveServiceDeploymentDeleteAction(AzureBaseAction):
    """Delete AI Foundry Cognitive Services deployments.

    A custom delete action is required for this child resource because the
    generic ARM delete path resolves api-version from the resource id. For
    deployment ids this can select an incompatible version, so we always call
    ``begin_delete_by_id`` with the resource's explicit api_version.
    """

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
    """Register explicit delete action for nested deployment resources.

    The default ARM delete action resolves api-version from resource id via
    ``session.resource_api_version(resource['id'])``. This runs as a
    ``resources.subscribe`` callback so it overrides the generic ARM delete
    action when this specific resource class is registered.
    """
    if resource_class is AiFoundryCognitiveServiceDeployment:
        resource_class.action_registry.register(
            'delete',
            AiFoundryCognitiveServiceDeploymentDeleteAction,
        )


resources.subscribe(register_ai_foundry_cognitive_service_deployment_actions)


# Reuse the Cognitive Services deployment implementation for AI Foundry.
# Both resources use the same ARM endpoint path; AI Foundry differs by
# api-version only. This subclass isolates that version override without
# changing the base deployment resource behavior.
@resources.register('ai-foundry-deployment')
class AiFoundryDeployment(AiFoundryCognitiveServiceDeployment):
    """Azure AI Foundry Deployment Resource.

    Shares the same endpoint path as
    ``azure.ai-foundry-cognitiveservice-deployment`` but uses the AI Foundry
    API version ``2025-06-01``.
    """

    class resource_type(AiFoundryCognitiveServiceDeployment.resource_type):
        api_version = '2025-06-01'


def register_ai_foundry_deployment_actions(registry, resource_class):
    """Register explicit delete action for nested deployment resources.

    The default ARM delete action resolves api-version from resource id via
    ``session.resource_api_version(resource['id'])``. This runs as a
    ``resources.subscribe`` callback so it overrides the generic ARM delete
    action when this specific resource class is registered.
    """
    if resource_class is AiFoundryDeployment:
        resource_class.action_registry.register(
            'delete', AiFoundryCognitiveServiceDeploymentDeleteAction
        )


resources.subscribe(register_ai_foundry_deployment_actions)
