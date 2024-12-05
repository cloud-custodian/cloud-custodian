# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestBatchComputeEnvironment(BaseTest):

    def test_batch_compute_tag(self):
        session_factory = self.replay_flight_data('test_batch_compute_tag')
        p = self.load_policy(
            {
                'name': 'batch-compute-tag',
                'resource': 'batch-compute',
                'filters': [
                    {'tag:team': 'absent'},
                    {'tag:owner': 'c7n'},
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'team': 'policy'}
                    },
                    {
                        'type': 'remove-tag',
                        'tags': ['owner']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('batch')
        tags = client.list_tags_for_resource(
            resourceArn=resources[0]['computeEnvironmentArn']
        )['tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, {'team': 'policy'})

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

    def test_definition_tag(self):
        session_factory = self.replay_flight_data('test_batch_definition_tag')
        p = self.load_policy(
            {
                'name': 'batch-definition-tag',
                'resource': 'batch-definition',
                'filters': [
                    {'tag:team': 'absent'},
                    {'tag:owner': 'c7n'},
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'team': 'policy'}
                    },
                    {
                        'type': 'remove-tag',
                        'tags': ['owner']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('batch')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['jobDefinitionArn'])['tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, {'team': 'policy'})

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


class TestBatchJobQueue(BaseTest):

    def test_batch_queue_tag(self):
        session_factory = self.replay_flight_data('test_batch_queue_tag')
        p = self.load_policy(
            {
                'name': 'batch-queue-tag',
                'resource': 'batch-queue',
                'filters': [
                    {'tag:team': 'absent'},
                    {'tag:owner': 'c7n'},
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'team': 'policy'}
                    },
                    {
                        'type': 'remove-tag',
                        'tags': ['owner']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('batch')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['jobQueueArn'])['tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, {'team': 'policy'})

    def test_batch_queue_update(self):
        session_factory = self.replay_flight_data("test_batch_queue_update")
        p = self.load_policy(
            {
                "name": "batch-queue-test",
                "resource": "batch-queue",
                "filters": [{"state": "ENABLED"}],
                "actions": [{"type": "update", "state": "DISABLED"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("batch")
        envs = client.describe_job_queues(
            jobQueues=[resources[0]["jobQueueName"]]
        )[
            "jobQueues"
        ]
        self.assertEqual(envs[0]["state"], "DISABLED")

    def test_batch_queue_delete(self):
        session_factory = self.replay_flight_data("test_batch_queue_delete")
        p = self.load_policy(
            {
                "name": "batch-queue-test",
                "resource": "batch-queue",
                "filters": [{"state": "DISABLED"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("batch")
        envs = client.describe_job_queues(
            jobQueues=[resources[0]['jobQueueName']]
        )['jobQueues']
        self.assertEqual(envs[0]['status'], 'DELETING')
