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
from c7n_azure.utils import ResourceIdParser

RESOURCE_ID = ("/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/"
                            "rgtest/providers/Microsoft.Compute/virtualMachines/nametest")

class UtilsTest(BaseTest):
    def setUp(self):
        super(UtilsTest, self).setUp()

    def test_get_namespace(self):
        self.assertEqual(ResourceIdParser.get_namespace(RESOURCE_ID), "Microsoft.Compute")

    def test_get_resource_group(self):
        self.assertEqual(ResourceIdParser.get_resource_group(RESOURCE_ID), "rgtest")

    def test_get_resource_type(self):
        self.assertEqual(ResourceIdParser.get_resource_type(RESOURCE_ID), "virtualMachines")

    def test_resource_name(self):
        self.assertEqual(ResourceIdParser.get_resource_name(RESOURCE_ID), "nametest")
