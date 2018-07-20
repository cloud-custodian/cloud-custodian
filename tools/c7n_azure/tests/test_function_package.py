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

import json

from azure_common import BaseTest
from c7n_azure.function_package import FunctionPackage


class FunctionPackageTest(BaseTest):
    def setUp(self):
        super(FunctionPackageTest, self).setUp()

    def test_add_function_config_periodic(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
            'mode':
                {'type': 'azure-periodic',
                 'schedule': '0 1 0 0 0'}
        })

        packer = FunctionPackage(p.data['name'])

        config = packer.get_function_config(p.data)

        binding = json.loads(config)

        self.assertEqual(binding['bindings'][0]['type'], 'timerTrigger')
        self.assertEqual(binding['bindings'][0]['name'], 'input')
        self.assertEqual(binding['bindings'][0]['schedule'], '0 1 0 0 0')

    def test_add_function_config_events(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
            'mode':
                {'type': 'azure-stream'}
        })

        packer = FunctionPackage(p.data['name'])

        config = packer.get_function_config(p.data)

        binding = json.loads(config)

        self.assertEqual(binding['bindings'][0]['type'], 'httpTrigger')

    def test_add_policy(self):
        p = self.load_policy({
            'name': 'test-azure-public-ip',
            'resource': 'azure.publicip',
            'mode':
                {'type': 'azure-stream'}
        })

        packer = FunctionPackage(p.data['name'])

        policy = json.loads(packer._get_policy(p.data))

        self.assertEqual(policy['policies'][0],
                         {u'resource': u'azure.publicip',
                          u'name': u'test-azure-public-ip',
                          u'mode': {u'type': u'azure-stream'}})
