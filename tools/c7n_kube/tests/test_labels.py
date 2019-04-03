# Copyright 2019 Capital One Services, LLC
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


class TestLabelAction(KubeTest):
    def test_label_action(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                'name': 'label-namespace',
                'resource': 'k8s.namespace',
                'filters': [
                    {'metadata.labels': None},
                    {'metadata.name': 'test'}
                ],
                'actions': [
                    {
                        'type': 'label',
                        'labels': {'test': 'value'}
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertTrue(resources)
        client = factory().client(group='Core', version='V1')
        resources = client.list_namespace().to_dict()['items']
        test_namespace = [r for r in resources if r['metadata']['name'] == 'test']
        self.assertEqual(len(test_namespace), 1)
        labels = test_namespace[0]['metadata']['labels']
        self.assertEqual(labels, {'test': 'value'})

    def test_namespaced_label_action(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                'name': 'label-service',
                'resource': 'k8s.service',
                'filters': [
                    {'metadata.labels.test': 'absent'},
                    {'metadata.name': 'hello-node'}
                ],
                'actions': [
                    {
                        'type': 'label',
                        'labels': {'test': 'value'}
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertTrue(resources)
        client = factory().client(group='Core', version='V1')
        resources = client.list_service_for_all_namespaces().to_dict()['items']
        test_namespace = [r for r in resources if r['metadata']['name'] == 'hello-node']
        self.assertEqual(len(test_namespace), 1)
        labels = test_namespace[0]['metadata']['labels']
        self.assertTrue('test' in labels.keys())
        self.assertEqual(labels['test'], 'value')
