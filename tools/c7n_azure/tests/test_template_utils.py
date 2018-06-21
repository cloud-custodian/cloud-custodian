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
from __future__ import absolute_import, division, print_function, unicode_literals

from azure_common import BaseTest
from c7n_azure.session import Session
from c7n_azure.template_utils import TemplateUtilities


class TemplateUtilsTest(BaseTest):
    def setUp(self):
        super(TemplateUtilsTest, self).setUp()
        self.template_util = TemplateUtilities()

    def test_deploy_template_with_parameters(self):
        s = Session()
        client = s.client('azure.mgmt.resource.ResourceManagementClient')

        group_name = 'cloud-custodian-test'
        self.template_util.create_resource_group(group_name, {'location': 'West US 2'})
        resource_group = client.resource_groups.get(group_name)

        self.assertIsNotNone(resource_group)

        template_file = 'dedicated_functionapp.json'
        parameters = self.template_util.get_default_parameters(
            'dedicated_functionapp.test.parameters.json')
        self.template_util.deploy_resource_template(group_name, template_file, parameters)

        resources = client.resources.list_by_resource_group(group_name)
        self.assertIsNotNone(resources)

        # Cleaning up resource group
        client.resource_groups.delete('cloud-custodian-test')

    def test_get_json_template(self):
        template_file_name = 'dedicated_functionapp.json'
        template = self.template_util.get_json_template(template_file_name)

        self.assertIsNotNone(template)

    def test_get_default_parameters(self):
        params_file_name = 'dedicated_functionapp.test.parameters.json'
        params_file = self.template_util.get_json_template(params_file_name)

        params = self.template_util.get_default_parameters(params_file_name)

        self.assertEqual(params_file['parameters'], params)

    def test_update_parameters(self):
        params_file_name = 'dedicated_functionapp.test.parameters.json'
        params_to_update = {
            'location': 'test_location',
            'appInsightsLocation': 'test_location_2'
        }
        params = self.template_util.get_default_parameters(params_file_name)
        updated_params = self.template_util.update_parameters(params, params_to_update)

        self.assertEqual(updated_params['location']['value'], params_to_update['location'])
        self.assertEqual(
            updated_params['appInsightsLocation']['value'], params_to_update['appInsightsLocation'])
