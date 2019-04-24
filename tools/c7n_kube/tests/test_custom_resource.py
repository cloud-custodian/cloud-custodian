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
#

from c7n.exceptions import PolicyValidationError

from common_kube import KubeTest


class TestCustomResource(KubeTest):
    def test_custom_cluster_resource_query(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'custom-resources',
                'resource': 'k8s.custom-cluster-resource',
                'query': [
                    {
                        'group': 'stable.example.com',
                        'version': 'v1',
                        'plural': 'crontabscluster'
                    }
                ]
            },
            session_factory=factory
        )

        resources = policy.run()
        self.assertTrue(len(resources), 1)
        self.assertEqual(resources[0]['apiVersion'], 'stable.example.com/v1')
        self.assertEqual(resources[0]['kind'], 'CronTabCluster')

    def test_custom_namespaced_resource_query(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'custom-resources',
                'resource': 'k8s.custom-namespaced-resource',
                'query': [
                    {
                        'group': 'stable.example.com',
                        'version': 'v1',
                        'plural': 'crontabs'
                    }
                ]
            },
            session_factory=factory
        )

        resources = policy.run()
        self.assertTrue(len(resources), 1)
        self.assertEqual(resources[0]['apiVersion'], 'stable.example.com/v1')
        self.assertEqual(resources[0]['kind'], 'CronTab')

    def test_custom_resource_validation(self):
        self.assertRaises(PolicyValidationError,
            self.load_policy,
            {
                'name': 'custom-resources',
                'resource': 'k8s.custom-namespaced-resource',
            },
            validate=True
        )

        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                'name': 'custom-resources',
                'resource': 'k8s.custom-namespaced-resource',
                'query': [
                    {'bad': 'value'}
                ]
            },
            validate=True
        )
