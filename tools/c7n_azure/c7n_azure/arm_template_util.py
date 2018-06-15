# Copyright 2015-2017 Capital One Services, LLC
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
"""
Generic arm template resource utilities
"""
import json
import os.path

from azure.mgmt.resource.resources.models import DeploymentMode
from c7n_azure.session import Session

from c7n.utils import local_session


class ArmTemplateUtil(object):
    def __init__(self):
        s = local_session(Session)
        #: :type: azure.mgmt.resource.ResourceManagementClient
        self.client = s.client('azure.mgmt.resource.ResourceManagementClient')

    def create_resource_group(self, group_name, group_parameters={'location': 'westus2'}):
        self.client.resource_groups.create_or_update(group_name, group_parameters)

    def deploy_resource_template(self, group_name, template_file_name, template_parameters=None, deployment_name='cloud-custodian'):
        arm_template = self.get_json_template(template_file_name)
        deployment_properties = {
            'mode': DeploymentMode.incremental,
            'template': arm_template,
        }

        if template_parameters:
            deployment_properties['parameters'] = template_parameters

        deployment_async_op = self.client.deployments.create_or_update(group_name, deployment_name, deployment_properties)
        deployment_async_op.wait()

    def get_default_parameters(self, file_name):
        json_parameters_file = self.get_json_template(file_name)
        return json_parameters_file['parameters']

    @staticmethod
    def get_json_template(file_name):
        file_path = os.path.join(os.path.dirname(__file__), 'templates', file_name)
        with open(file_path, 'r') as template_file:
            json_template = json.load(template_file)

        return json_template

    @staticmethod
    def update_parameters(parameters, updated_parameters):
        for key, value in list(updated_parameters.items()):
            parameters[key]['value'] = value

        return parameters

    @staticmethod
    def generate_resource_name(name):
        return name.replace(' ', '-').lower()

    @staticmethod
    def generate_storage_name(name):
        return





if __name__ == '__main__':
    self = ArmTemplateUtil()
    # new_parameters = {
    #     'name': 'erwelch-functions-again',
    #     'location': 'westus'
    # }
    #
    # params = self.get_default_parameters('testing.parameters.json')
    # new_params = self.update_parameters(params, new_parameters)

    my_group_name = 'andy-linux-container1'
    self.create_resource_group(my_group_name)
    paramters = self.get_default_parameters('dedicated_functionapp.parameters.json')
    self.deploy_resource_template(my_group_name, 'dedicated_functionapp.json', paramters)

