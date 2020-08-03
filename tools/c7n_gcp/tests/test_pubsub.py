# Copyright 2019 Capital One Services, LLC
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest, event_data


class PubSubTopicTest(BaseTest):

    def test_pubsub_topic_query(self):
        project_id = 'cloud-custodian'
        pubsub_topic_name = 'projects/cloud-custodian/topics/custodian'
        session_factory = self.replay_flight_data(
            'pubsub-topic-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-pubsub-topic-dryrun',
             'resource': 'gcp.pubsub-topic'},
            session_factory=session_factory)

        pubsub_topic_resources = policy.run()
        self.assertEqual(pubsub_topic_resources[0]['name'], pubsub_topic_name)

    def test_pubsub_topic_get(self):
        project_id = 'cloud-custodian'
        pubsub_topic_name = 'projects/cloud-custodian/topics/custodian'
        session_factory = self.replay_flight_data(
            'pubsub-topic-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-pubsub-topic-dryrun',
             'resource': 'gcp.pubsub-topic'},
            session_factory=session_factory)

        pubsub_topic_resource = policy.resource_manager.get_resource(
            {'project_id': project_id, 'topic_id': pubsub_topic_name})
        self.assertEqual(pubsub_topic_resource['name'], pubsub_topic_name)


class PubSubSubscriptionTest(BaseTest):

    def test_pubsub_subscription_query(self):
        project_id = 'cloud-custodian'
        pubsub_subscription_name = 'projects/cloud-custodian/subscriptions/custodian'
        session_factory = self.replay_flight_data(
            'pubsub-subscription-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-pubsub-subscription-dryrun',
             'resource': 'gcp.pubsub-subscription'},
            session_factory=session_factory)

        pubsub_subscription_resources = policy.run()
        self.assertEqual(pubsub_subscription_resources[0]['name'], pubsub_subscription_name)

    def test_pubsub_subscription_get(self):
        project_id = 'cloud-custodian'
        subscription_name = 'custodian'
        resource_name = 'projects/{}/subscriptions/{}'.format(project_id, subscription_name)
        session_factory = self.replay_flight_data(
            'pubsub-subscription-get', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-pubsub-subscription-audit',
             'resource': 'gcp.pubsub-subscription',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['google.pubsub.v1.Subscriber.CreateSubscription']
             }},
            session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('pubsub-subscription-create.json')
        resources = exec_mode.run(event, None)
        self.assertEqual(resources[0]['name'], resource_name)


class PubSubSnapshotTest(BaseTest):

    def test_pubsub_snapshot_query(self):
        project_id = 'cloud-custodian'
        pubsub_snapshot_name = 'projects/cloud-custodian/snapshots/custodian'
        session_factory = self.replay_flight_data(
            'pubsub-snapshot-query', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-pubsub-snapshot-dryrun',
             'resource': 'gcp.pubsub-snapshot'},
            session_factory=session_factory)

        pubsub_snapshot_resources = policy.run()
        self.assertEqual(pubsub_snapshot_resources[0]['name'], pubsub_snapshot_name)
