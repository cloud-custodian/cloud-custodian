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

    test.assertEqual(
        policy.resource_manager.get_urns(resources),
        ["gcp:pubsub::cloud-custodian:topic/test_topic"],
    )


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

    test.assertEqual(
        policy.resource_manager.get_urns(resources),
        ["gcp:pubsub::cloud-custodian:subscription/c7n-subscription"],
    )


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
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            ["gcp:pubsub::cloud-custodian:subscription/custodian"],
        )


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
        self.assertEqual(
            policy.resource_manager.get_urns(pubsub_snapshot_resources),
            ["gcp:pubsub::cloud-custodian:snapshot/custodian"],
        )


class PubSubTopicTest(BaseTest):

    def test_pubsub_topic_filter_iam_query(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data('pubsub-topic-filter-iam', project_id=project_id)
        p = self.load_policy({
            'name': 'pubsub-topic-filter-iam',
            'resource': 'gcp.pubsub-topic',
            'filters': [{
                'type': 'iam-policy',
                'doc': {'key': 'bindings[*].members[]',
                        'op': 'intersect',
                        'value': ['allUsers', 'allAuthenticatedUsers']}
            }]
        }, session_factory=factory)
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('projects/cloud-custodian/topics/custodian-test-iam-topic',
                         resources[0]['name'])
