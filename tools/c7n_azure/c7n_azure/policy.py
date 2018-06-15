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

from c7n.policy import PolicyExecutionMode, Policy
from c7n.registry import PluginRegistry
from c7n_azure.arm_template_util import ArmTemplateUtil
from c7n import utils

execution = PluginRegistry('azure.execution')

@execution.register('azure-function')
class AzureFunctionMode(PolicyExecutionMode):
    """A policy that runs/executes in azure functions."""

    azure_function_schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'execution-options': {
                'type': 'object',
                'sku': 'string',
                'location': 'string',
                'workerSize': 'number',
                'skuCode': 'string'
            }
        }
    }

    schema = utils.type_schema('azure-function', rinherit=azure_function_schema)

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        """Provision any resources needed for the policy."""
        util = ArmTemplateUtil()
        name = self.policy.data['name'].replace(' ', '-').lower()
        util.create_resource_group(name)
        parameters = self.get_parameters()
        util.deploy_resource_template('dedicated_functionapp.json', parameters)

    def get_parameters(self):
        util = ArmTemplateUtil()
        name = self.policy.data['name'].replace(' ', '-').lower()
        parameters = util.get_default_parameters('dedicated_functionapp.parameters.json')
        p = self.policy.data
        if 'mode' in p:
            if 'execution-options' in p['mode']:
                updated_parameters = p['mode']['execution-options']
                updated_parameters['name'] = name
                util.update_parameters(parameters, updated_parameters)

        return parameters

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("subclass responsibility")

    def validate(self):
        """Validate configuration settings for execution mode."""


class AzurePolicy(Policy):

    EXEC_MODE_MAP = {
        'azure-function': AzureFunctionMode
    }

    def get_execution_mode(self):
        exec_mode_type = self.data.get('mode', {'type': 'pull'}).get('type')
        return self.EXEC_MODE_MAP[exec_mode_type](self)