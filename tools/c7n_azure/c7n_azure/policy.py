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

import json
import logging

from c7n_azure.function_package import FunctionPackage
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.template_utils import TemplateUtilities
from c7n_azure.constants import CONST_DOCKER_VERSION, CONST_FUNCTIONS_EXT_VERSION

from c7n import utils
from c7n.policy import ServerlessExecutionMode, PullMode, execution
from c7n.utils import local_session


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
            },
            'execution-options': {'type': 'object'}
        }
    }

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    def __init__(self, policy):
        self.policy = policy
        self.log = logging.getLogger('custodian.azure.AzureFunctionMode')
        s = local_session(self.policy.session_factory)
        self.client = s.client('azure.mgmt.web.WebSiteManagementClient')

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        """Provision any resources needed for the policy."""
        template_util = TemplateUtilities()

        parameters = self._get_parameters(template_util)
        group_name = parameters['servicePlanName']['value']
        webapp_name = parameters['name']['value']
        policy_name = self.policy.data['name'].replace(' ', '-').lower()

        existing_service_plan = self.client.app_service_plans.get(
            group_name, parameters['servicePlanName']['value'])

        if not existing_service_plan:
            template_util.create_resource_group(
                group_name, {'location': parameters['location']['value']})

            template_util.deploy_resource_template(
                group_name, 'dedicated_functionapp.json', parameters).wait()

        else:
            existing_webapp = self.client.web_apps.get(group_name, webapp_name)
            if not existing_webapp:
                functionapp_util = FunctionAppUtilities()
                functionapp_util.deploy_webapp(webapp_name, group_name, existing_service_plan,
                                               parameters['storageName']['value'])
            else:
                self.log.info("Found existing App %s (%s) in group %s" %
                              (webapp_name, existing_webapp.location, group_name))

        self.log.info("Building function package for %s" % webapp_name)

        archive = FunctionPackage(policy_name)
        archive.build(self.policy.data)
        archive.close()

        if archive.wait_for_status(webapp_name):
            archive.publish(webapp_name)
        else:
            self.log.error("Aborted deployment, ensure Application Service is healthy.")

    def _get_parameters(self, template_util):
        parameters = template_util.get_default_parameters(
            'dedicated_functionapp.parameters.json')

        data = self.policy.data

        updated_parameters = {
            'name': (data['mode']['provision-options']['servicePlanName'] +
                     '-' +
                     data['name']).replace(' ', '-').lower(),

            'storageName': (data['mode']['provision-options']['servicePlanName']
                            ).replace('-', '').lower(),
            'dockerVersion': CONST_DOCKER_VERSION,
            'functionsExtVersion': CONST_FUNCTIONS_EXT_VERSION
        }

        if 'mode' in data:
            if 'provision-options' in data['mode']:
                updated_parameters.update(data['mode']['provision-options'])

        parameters = template_util.update_parameters(parameters, updated_parameters)

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
        self.log.info(json.dumps(lambda_context))
        raise NotImplementedError("error - not implemented")

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")
