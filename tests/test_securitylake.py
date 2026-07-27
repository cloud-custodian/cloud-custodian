# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class SecurityLakeDataLakeTest(BaseTest):

    def test_security_lake_query(self):
        session_factory = self.replay_flight_data('test_security_lake_query')
        p = self.load_policy(
            {
                'name': 'security-lake',
                'resource': 'aws.security-lake',
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['dataLakeArn'])
        self.assertEqual(resources[0]['region'], 'us-east-1')
        self.assertEqual(
            resources[0]['Tags'], [{'Key': 'Env', 'Value': 'prod'}])

    def test_security_lake_tag(self):
        session_factory = self.replay_flight_data('test_security_lake_tag')
        p = self.load_policy(
            {
                'name': 'security-lake-tag',
                'resource': 'aws.security-lake',
                'filters': [{'tag:owner': 'absent'}],
                'actions': [{'type': 'tag', 'key': 'owner', 'value': 'security'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('securitylake')
        tags = client.list_tags_for_resource(
            resourceArn=resources[0]['dataLakeArn'])['tags']
        self.assertIn({'key': 'owner', 'value': 'security'}, tags)

        p = self.load_policy(
            {
                'name': 'security-lake-untag',
                'resource': 'aws.security-lake',
                'filters': [{'tag:owner': 'present'}],
                'actions': [{'type': 'remove-tag', 'tags': ['owner']}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(
            resourceArn=resources[0]['dataLakeArn'])['tags']
        self.assertEqual(tags, [])

    def test_security_lake_delete(self):
        session_factory = self.replay_flight_data('test_security_lake_delete')
        p = self.load_policy(
            {
                'name': 'security-lake-delete',
                'resource': 'aws.security-lake',
                'actions': ['delete'],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('securitylake')
        self.assertEqual(client.list_data_lakes().get('dataLakes'), [])


class SecurityLakeSubscriberTest(BaseTest):

    def test_security_lake_subscriber_query(self):
        session_factory = self.replay_flight_data(
            'test_security_lake_subscriber_query')
        p = self.load_policy(
            {
                'name': 'security-lake-subscriber',
                'resource': 'aws.security-lake-subscriber',
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['subscriberArn'])
        self.assertEqual(resources[0]['subscriberName'], 'test-subscriber')
        self.assertEqual(
            resources[0]['Tags'], [{'Key': 'Env', 'Value': 'prod'}])

    def test_security_lake_subscriber_tag(self):
        session_factory = self.replay_flight_data(
            'test_security_lake_subscriber_tag')
        p = self.load_policy(
            {
                'name': 'security-lake-subscriber-tag',
                'resource': 'aws.security-lake-subscriber',
                'filters': [{'tag:owner': 'absent'}],
                'actions': [{'type': 'tag', 'key': 'owner', 'value': 'security'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('securitylake')
        tags = client.list_tags_for_resource(
            resourceArn=resources[0]['subscriberArn'])['tags']
        self.assertIn({'key': 'owner', 'value': 'security'}, tags)

        p = self.load_policy(
            {
                'name': 'security-lake-subscriber-untag',
                'resource': 'aws.security-lake-subscriber',
                'filters': [{'tag:owner': 'present'}],
                'actions': [{'type': 'remove-tag', 'tags': ['owner']}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(
            resourceArn=resources[0]['subscriberArn'])['tags']
        self.assertEqual(tags, [])

    def test_security_lake_subscriber_delete(self):
        session_factory = self.replay_flight_data(
            'test_security_lake_subscriber_delete')
        p = self.load_policy(
            {
                'name': 'security-lake-subscriber-delete',
                'resource': 'aws.security-lake-subscriber',
                'actions': ['delete'],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('securitylake')
        self.assertEqual(client.list_subscribers().get('subscribers'), [])
