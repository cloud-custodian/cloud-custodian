# Copyright 2019 Microsoft Corporation
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
from c7n_azure.utils import get_service_tag_ip_space


class UtilsTest(BaseTest):

    def test_get_service_tag_ip_space(self):
        # Intentionally vague assertions as it will change next time we record cassettes.
        # I want to use a real cassette since it is a preview API and the
        # schema may change which we'll want to catch in functionals.

        # Should only be a few of these
        result = get_service_tag_ip_space('ApiManagement', 'eastus2')
        self.assertTrue(len(result) < 20)

        # This is in all regions, so it must be larger than previous
        larger_result = get_service_tag_ip_space('ApiManagement')
        self.assertTrue(len(larger_result) > len(result))

        # Total IP space, will be around 2500
        result = get_service_tag_ip_space()
        self.assertTrue(len(result) > 2000)
