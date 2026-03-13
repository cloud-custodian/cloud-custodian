# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import requests

from c7n_azure import constants
from c7n_azure.provider import resources
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n.utils import type_schema


@resources.register('cognitiveservice-deployment')
class CognitiveServiceDeployment(ChildArmResourceManager):
    """Cognitive Services Deployment Resource
    Supports read/list and delete operations for
    ``Microsoft.CognitiveServices/accounts/deployments``.

    Deployment-level tagging is intentionally unsupported for this resource type.
    Tags shown in Azure Portal are typically account-level tags on the parent
    ``Microsoft.CognitiveServices/accounts`` resource.

    :example:

    Finds all failed model deployments under Cognitive Services accounts.

    .. code-block:: yaml

        policies:
          - name: cognitiveservice-deployments-failed
            resource: azure.cognitiveservice-deployment
            filters:
              - type: value
                key: properties.provisioningState
                value: Failed
    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']
        api_version = '2024-10-01'

        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        # Enumeration uses a direct ARM REST call in enumerate_resources.
        enum_spec = ('resources', 'list', None)
        parent_manager_name = 'cognitiveservice'
        resource_type = 'Microsoft.CognitiveServices/accounts/deployments'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'type'
        )

    def enumerate_resources(self, parent_resource, type_info, vault_url=None, **params):
        # Generic ARM /resources listing does not reliably return deployment children.
        # Query the deployments endpoint per Cognitive Services account parent.
        session = self.get_session()
        session._initialize_session()
        token = session.credentials.get_token(constants.RESOURCE_GLOBAL_MGMT + '.default')

        url = (
            f"{constants.RESOURCE_GLOBAL_MGMT}subscriptions/{session.get_subscription_id()}"
            f"/resourceGroups/{parent_resource['resourceGroup']}"
            f"/providers/Microsoft.CognitiveServices/accounts/{parent_resource['name']}"
            f"/deployments?api-version={self.resource_type.api_version}"
        )
        headers = {
            'Authorization': f'Bearer {token.token}',
            'Content-Type': 'application/json'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json().get('value', [])

    def get_resources(self, resource_ids):
        client = self.get_client()
        data = [
            client.resources.get_by_id(resource_id, self.resource_type.api_version)
            for resource_id in resource_ids
        ]
        return self.augment([r.serialize(True) for r in data])


class CognitiveServiceDeploymentDeleteAction(AzureBaseAction):
    """Delete Cognitive Services deployments."""

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


def register_cognitive_service_deployment_actions(registry, resource_class):
    if resource_class is CognitiveServiceDeployment:
        resource_class.action_registry.register('delete', CognitiveServiceDeploymentDeleteAction)


resources.subscribe(register_cognitive_service_deployment_actions)
