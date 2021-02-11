# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from msrestazure.azure_exceptions import CloudError

from c7n_azure.provisioning.deployment_unit import DeploymentUnit


class ResourceGroupUnit(DeploymentUnit):

    def __init__(self):
        super(ResourceGroupUnit, self).__init__(
            'azure.mgmt.resource.ResourceManagementClient')
        self.type = "Resource Group"

    def verify_params(self, params):
        return set(params.keys()) == set({'name', 'location'})

    def _get(self, params):
        try:
            return self.client.resource_groups.get(params['name'])
        except CloudError:
            return None

    def _provision(self, params):
        return self.client.resource_groups.create_or_update(params['name'],
                      {'location': params['location']})
