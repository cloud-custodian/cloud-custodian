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
from .common import BaseTest
from c7n_azure.session import Session


class VMClientTest(BaseTest):
    def setUp(self):
        super(VMClientTest, self).setUp()
        session = Session()
        self.client = session.client('azure.mgmt.compute.ComputeManagementClient')

    def test_client(self):
        """Simple example showing a VCR recorded test working"""
        machines = list(self.client.virtual_machines.list_all())
        self.assertGreater(len(machines), 1)
