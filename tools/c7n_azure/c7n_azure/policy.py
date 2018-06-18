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

from c7n_azure.template_utils import TemplateUtil

from c7n import utils
from c7n.policy import ServerlessExecutionMode, execution


@execution.register('azure-function')
class AzureFunctionMode(ServerlessExecutionMode):
    """A policy that runs/executes in azure functions."""

    azure_function_schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'execution-options': {
                'type': 'object',
                'sku': 'string',
                'location': 'string',
                'appInsightsLocation': 'string',
                'workerSize': 'number',
                'skuCode': 'string'
            }
        }
    }

    schema = utils.type_schema('azure-function', rinherit=azure_function_schema)

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    def __init__(self, policy):
        super(policy)
        self.template_util = TemplateUtil()

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        """Provision any resources needed for the policy."""
        policy_name = self.policy.data['name'].replace(' ', '-').lower()

        parameters = self.get_parameters(policy_name)
        self.template_util.create_resource_group(policy_name, {'location': parameters['location']['value']})
        self.template_util.deploy_resource_template(policy_name, 'dedicated_functionapp.json', parameters)

    def get_parameters(self, policy_name):
        parameters = self.template_utilutil.get_default_parameters('dedicated_functionapp.parameters.json')
        updated_parameters = {}

        p = self.policy.data
        if 'mode' in p:
            if 'execution-options' in p['mode']:
                updated_parameters = p['mode']['execution-options']

        updated_parameters['name'] = policy_name
        updated_parameters['storageName'] = policy_name.replace('-', '')
        self.template_util.update_parameters(parameters, updated_parameters)

        return parameters

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("subclass responsibility")

    def validate(self):
        """Validate configuration settings for execution mode."""
