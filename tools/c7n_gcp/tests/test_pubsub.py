# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest, event_data

from pytest_terraform import terraform


@terraform('pubsub_topic')
def test_pubsub_topic_query(test, pubsub_topic):
    topic_name = pubsub_topic['google_pubsub_topic.test_topic.id']

    session_factory = test.replay_flight_data('pubsub-topic-query')

    policy = test.load_policy(
        {'name': 'gcp-pubsub-topic-dryrun',
         'resource': 'gcp.pubsub-topic'},
        session_factory=session_factory)

    resource = policy.resource_manager.get_resource(
        {'project_id': test.project_id, 'topic_id': topic_name}
    )
    test.assertEqual(resource['name'], topic_name)

    resources = policy.run()
    topic_names = [r['name'] for r in resources]
    assert topic_name in topic_names


@terraform('pubsub_subscription')
def test_pubsub_subscription_query(test, pubsub_subscription):
    subscription_name = pubsub_subscription['google_pubsub_subscription.c7n.id']
    session_factory = test.replay_flight_data('pubsub-subscription-query')

    policy = test.load_policy(
        {'name': 'gcp-pubsub-subscription-dryrun',
         'resource': 'gcp.pubsub-subscription',
         'filters': [{'name': subscription_name}]},
        session_factory=session_factory)

    resources = policy.run()
    test.assertEqual(resources[0]['name'], subscription_name)


class PubSubSubscriptionTest(BaseTest):
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
