# Copyright 2018-2019 Capital One Services, LLC
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
from common_kube import KubeTest


class NamespaceTest(KubeTest):

    def test_ns_query(self):
        p = self.load_policy({
            'name': 'all-namespaces',
            'resource': 'k8s.namespace'})
        resources = p.run()
        self.assertEqual(len(resources), 3)
        self.assertEqual(
            sorted([r['metadata']['name'] for r in resources]),
            ['default', 'kube-public', 'kube-system'])
