# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.cognitive_service_deployment import (
    CognitiveServiceDeployment,
    CognitiveServiceDeploymentDeleteAction,
)


# The only difference between AiFoundryDeployment and CognitiveServiceDeployment is
# the API version, so we can reuse the same implementation for both resources.Created a seperate
# to handle it this api version change without affecting the existing CognitiveServiceDeployment
# resource.
@resources.register('ai-foundry-deployment')
class AiFoundryDeployment(CognitiveServiceDeployment):
    """Azure AI Foundry Deployment Resource.

    Shares implementation with ``azure.cognitiveservice-deployment`` but uses
    the AI Foundry API version.
    """

    class resource_type(CognitiveServiceDeployment.resource_type):
        api_version = '2025-06-01'


def register_ai_foundry_deployment_actions(registry, resource_class):
    if resource_class is AiFoundryDeployment:
        resource_class.action_registry.register('delete', CognitiveServiceDeploymentDeleteAction)


resources.subscribe(register_ai_foundry_deployment_actions)
