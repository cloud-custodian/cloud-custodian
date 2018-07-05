# Copyright 2015-2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from c7n_azure.function_package import FunctionPackage
from c7n_azure.template_utils import TemplateUtilities

from c7n import utils
from c7n.policy import ServerlessExecutionMode, PullMode, execution


class AzureFunctionMode(ServerlessExecutionMode):
    """A policy that runs/executes in azure functions."""

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'provision-options': {
                'type': 'object',
                'location': 'string',
                'appInsightsLocation': 'string',
                'servicePlanName': 'string',
                'sku': 'string',
                'workerSize': 'number',
                'skuCode': 'string'
            }
        }
    }

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    def __init__(self, policy):
        self.policy = policy
        self.template_util = TemplateUtilities()

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        """Provision any resources needed for the policy."""
        parameters = self.get_parameters()
        group_name = parameters['servicePlanName']['value']

        if not self.template_util.resource_exist(group_name, parameters['name']['value']):
            self.template_util.create_resource_group(
                group_name, {'location': parameters['location']['value']})

            self.template_util.deploy_resource_template(
                group_name, 'dedicated_functionapp.json', parameters).wait()

        archive = FunctionPackage(self.policy.data)
        archive.build()
        archive.publish(parameters['name']['value'])

    def get_parameters(self):
        parameters = self.template_util.get_default_parameters(
            'dedicated_functionapp.parameters.json')

        data = self.policy.data

        updated_parameters = {
            'name': (data['mode']['provision-options']['servicePlanName'] +
                     '-' +
                     data['name']).replace(' ', '-').lower(),

            'storageName': data['mode']['provision-options']['servicePlanName']
        }

        if 'mode' in data:
            if 'provision-options' in data['mode']:
                updated_parameters.update(data['mode']['provision-options'])

        parameters = self.template_util.update_parameters(parameters, updated_parameters)

        return parameters

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("subclass responsibility")

    def validate(self):
        """Validate configuration settings for execution mode."""


@execution.register('azure-periodic')
class AzurePeriodicMode(AzureFunctionMode, PullMode):
    """A policy that runs/executes in azure functions at specified
    time intervals."""
    schema = utils.type_schema('azure-periodic',
                               schedule={'type': 'string'},
                               rinherit=AzureFunctionMode.schema)

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        return PullMode.run(self)

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")


@execution.register('azure-stream')
class AzureStreamMode(AzureFunctionMode):
    """A policy that runs/executes in azure functions from an
    azure activity log stream."""

    schema = utils.type_schema('azure-stream', rinherit=AzureFunctionMode.schema)

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("error - not implemented")

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")
