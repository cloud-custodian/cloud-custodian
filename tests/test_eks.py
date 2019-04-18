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
from __future__ import absolute_import, division, print_function, unicode_literals

import time
from .common import BaseTest


class EKS(BaseTest):

    def test_query_with_subnet_sg_filter(self):
        factory = self.replay_flight_data("test_eks_query")
        p = self.load_policy(
            {
                "name": "eks",
                "resource": "eks",
                "filters": [
                    {'type': 'subnet',
                     'key': 'tag:kubernetes.io/cluster/dev',
                     'value': 'shared'},
                    {'type': 'security-group',
                     'key': 'tag:App',
                     'value': 'eks'}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'dev')

    def test_update_config(self):
        factory = self.replay_flight_data('test_eks_update_config')
        p = self.load_policy({
            'name': 'eksupdate',
            'resource': 'eks',
            'filters': [
                {'name': 'devk8s'},
                {'resourcesVpcConfig.endpointPublicAccess': True}],
            'actions': [{
                'type': 'update-config',
                'resourcesVpcConfig': {
                    'endpointPublicAccess': False,
                    'endpointPrivateAccess': True
                }}]}, session_factory=factory, config={'region': 'us-east-2'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(10)
        client = factory().client('eks')
        info = client.describe_cluster(name='devk8s')['cluster']
        self.assertEqual(resources[0]['status'], 'ACTIVE')
        self.assertEqual(info['status'], 'UPDATING')

    def test_delete_eks(self):
        factory = self.replay_flight_data("test_eks_delete")
        p = self.load_policy(
            {
                "name": "eksdelete",
                "resource": "eks",
                "filters": [{"name": "dev"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("eks")
        cluster = client.describe_cluster(name='dev').get('cluster')
        self.assertEqual(cluster['status'], 'DELETING')
