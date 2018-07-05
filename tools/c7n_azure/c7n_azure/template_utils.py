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
Generic ARM template resource utilities
"""
import json
import logging
import os.path

from azure.mgmt.resource.resources.models import DeploymentMode
from c7n_azure.session import Session

from c7n.utils import local_session


class TemplateUtilities(object):
    def __init__(self):
        s = local_session(Session)
        #: :type: azure.mgmt.resource.ResourceManagementClient
        self.client = s.client('azure.mgmt.resource.ResourceManagementClient')
        self.log = logging.getLogger('custodian.azure.template_utils')

    def create_resource_group(self, group_name, group_parameters):
        self.log.info("Create or update resource group: %s" % group_name)
        self.client.resource_groups.create_or_update(group_name, group_parameters)

    def deploy_resource_template(self, group_name, template_file_name, template_parameters=None):
        self.log.info("Deploy resource template: %s" % template_file_name)
        arm_template = self.get_json_template(template_file_name)
        deployment_properties = {
            'mode': DeploymentMode.incremental,
            'template': arm_template,
        }

        if template_parameters:
            deployment_properties['parameters'] = template_parameters

        return self.client.deployments.create_or_update(
            group_name, group_name, deployment_properties)

    def resource_exist(self, group_name, resource_name):
        if not self.client.resource_groups.check_existence(group_name):
            return False

        r_filter = ("name eq '%s'" % resource_name)

        for resource in self.client.resources.list_by_resource_group(group_name, filter=r_filter):
            return True
        return False

    def get_default_parameters(self, file_name):
        # deployment client expects only the parameters, not the full parameters file
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
