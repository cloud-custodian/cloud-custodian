# Copyright 2018 Capital One Services, LLC
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


from .common import BaseTest

from c7n.provider import clouds


class ProviderTest(BaseTest):

    def test_available_clouds(self):
        # the other providers are currently distributed as separate
        # installs (tools/c7n_azure and tools/c7n_gcp)
        self.assertEqual(sorted(clouds.keys()), ["aws", "azure", "gcp", "k8s"])
