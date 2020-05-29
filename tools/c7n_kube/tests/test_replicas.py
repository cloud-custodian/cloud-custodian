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


class TestReplicaAction(KubeTest):
    def test_replica_action_downscale(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                'name': 'replica-downscale',
                'resource': 'k8s.deployment',
                'filters': [
                    {'spec.replicas': 1},
                    {'metadata.name': 'nginx'}
                ],
                'actions': [
                    {
                        'type': 'replica',
                        'replicas': 0
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertTrue(resources)
        client = factory().client(group='Apps', version='V1')
        resources = client.list_namespace().to_dict()['items']
        test_namespace = [r for r in resources if r['metadata']['name'] == 'nginx']
        self.assertEqual(len(test_namespace), 1)
        replicas = test_namespace[0]['spec']['replicas']
        self.assertEqual(replicas, 0)

    def test_replica_action_upscale(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                'name': 'replica-upscale',
                'resource': 'k8s.deployment',
                'filters': [
                    {'spec.replicas': 1},
                    {'metadata.name': 'nginx'}
                ],
                'actions': [
                    {
                        'type': 'replica',
                        'replicas': 3
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        self.assertTrue(resources)
        client = factory().client(group='Apps', version='V1')
        resources = client.list_namespace().to_dict()['items']
        test_namespace = [r for r in resources if r['metadata']['name'] == 'nginx']
        self.assertEqual(len(test_namespace), 1)
        replicas = test_namespace[0]['spec']['replicas']
        self.assertEqual(replicas, 3)
