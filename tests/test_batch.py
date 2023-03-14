# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
