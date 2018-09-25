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
import re

from azure_common import BaseTest
from c7n_azure.session import Session


class SessionTest(BaseTest):
    def setUp(self):
        super(SessionTest, self).setUp()

    def test_api_version(self):
        """Verify we retrieve the correct API version for a resource type"""
        s = Session()
        client = s.client('azure.mgmt.resource.ResourceManagementClient')
        resource = next(client.resources.list())
        self.assertTrue(re.match('\\d{4}-\\d{2}-\\d{2}',
                                 s.resource_api_version(resource.id)) is not None)
