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

from .common import BaseTest


class TestBatchComputeEnvironment(BaseTest):

    def test_batch_compute_update(self):
        session_factory = self.replay_flight_data("test_batch_compute_update")
        p = self.load_policy(
            {
                "name": "batch-compute",
                "resource": "batch-compute",
                "filters": [{"computeResources.desiredvCpus": 0}, {"state": "ENABLED"}],
                "actions": [{"type": "update-environment", "state": "DISABLED"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("batch")
        envs = client.describe_compute_environments(
            computeEnvironments=[resources[0]["computeEnvironmentName"]]
        )[
            "computeEnvironments"
        ]
        self.assertEqual(envs[0]["state"], "DISABLED")

    def test_batch_compute_delete(self):
        session_factory = self.replay_flight_data("test_batch_compute_delete")
        p = self.load_policy(
            {
                "name": "batch-compute",
                "resource": "batch-compute",
                "filters": [{"computeResources.desiredvCpus": 0}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("batch")
        envs = client.describe_compute_environments(
            computeEnvironments=[resources[0]['computeEnvironmentName']]
        )['computeEnvironments']
        self.assertEqual(envs[0]['status'], 'DELETING')


class TestBatchDefinition(BaseTest):

    def test_definition_deregister(self):
        def_name = 'c7n_batch'
        session_factory = self.replay_flight_data(
            'test_batch_definition_deregister')
        p = self.load_policy({
            'name': 'batch-definition',
            'resource': 'batch-definition',
            'filters': [
                {'containerProperties.image': 'amazonlinux'}],
            'actions': [{'type': 'deregister'}]
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['jobDefinitionName'], 'c7n_batch')
        client = session_factory(region='us-east-1').client('batch')
        defs = client.describe_job_definitions(
            jobDefinitionName=def_name)['jobDefinitions']
        self.assertEqual(defs[0]['status'], 'INACTIVE')
