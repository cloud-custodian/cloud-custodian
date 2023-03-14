# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

from .common import BaseTest


class MessageQueue(BaseTest):

    def test_query_with_subnet_sg_filter(self):
        factory = self.replay_flight_data("test_mq_query")
        p = self.load_policy(
            {
                "name": "mq",
                "resource": "message-broker",
                "filters": [
                    {'type': 'subnet',
                     'key': 'tag:NetworkLocation',
                     'value': 'Public'},
                    {'type': 'security-group',
                     'key': 'tag:NetworkLocation',
                     'value': 'Private'}]
            },
            config={'region': 'us-east-1'},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['BrokerName'], 'dev')

    def test_metrics(self):
        factory = self.replay_flight_data('test_mq_metrics')
        p = self.load_policy(
            {'name': 'mq-metrics',
             'resource': 'message-broker',
             'filters': [{
                 'type': 'metrics',
                 'name': 'CpuUtilization',
                 'op': 'gt',
                 'value': 0,
                 'days': 1}]},
            config={'region': 'us-east-1'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['BrokerName'], 'dev')
        self.assertTrue('c7n.metrics' in resources[0])

    def test_mq_message_broker_kms_filter(self):
        session_factory = self.replay_flight_data('test_mq_message_broker_kms_filter')
        kms = session_factory().client('kms')
        p = self.load_policy(
            {
                'name': 'test-message-broker-kms-filter',
                'resource': 'message-broker',
                'filters': [
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/aws/mq'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['EncryptionOptions']['KmsKeyId'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/aws/mq')

    def test_delete_mq(self):
        factory = self.replay_flight_data("test_mq_delete")
        p = self.load_policy(
            {
                "name": "mqdel",
                "resource": "message-broker",
                "filters": [{"BrokerName": "dev"}],
                "actions": ["delete"],
            },
            config={'region': 'us-east-1'},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("mq")
        broker = client.describe_broker(BrokerId='dev')
        self.assertEqual(broker['BrokerState'], 'DELETION_IN_PROGRESS')

    def test_mq_tag_untag_markforop(self):
        factory = self.replay_flight_data("test_mq_tag_untag_markforop")
        p = self.load_policy(
            {
                "name": "mark-unused-mq-delete",
                "resource": "message-broker",
                'filters': [{'tag:Role': 'Dev'}],
                "actions": [
                    {'type': 'tag',
                     'tags': {'Env': 'Dev'}},
                    {'type': 'remove-tag',
                     'tags': ['Role']},
                    {'type': 'mark-for-op',
                     'op': 'delete',
                     'days': 2}]},
            config={'region': 'us-east-1'},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("mq")
        if self.recording:
            time.sleep(1)
        tags = client.list_tags(ResourceArn=resources[0]["BrokerArn"])["Tags"]
        self.assertEqual(
            {t['Key']: t['Value'] for t in resources[0]['Tags']},
            {'Role': 'Dev'})
        self.assertEqual(
            tags,
            {'Env': 'Dev',
             'maid_status': 'Resource does not meet policy: delete@2019/01/31'})

    def test_mq_config_tagging(self):
        factory = self.replay_flight_data("test_mq_config_tagging")
        p = self.load_policy(
            {
                "name": "mark-unused-mq-delete",
                "resource": "message-config",
                'filters': [{'tag:Role': 'Dev'}],
                "actions": [
                    {'type': 'tag',
                     'tags': {'Env': 'Dev'}},
                    {'type': 'remove-tag',
                     'tags': ['Role']}]},
            config={'region': 'us-east-1'},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client("mq")
        if self.recording:
            time.sleep(1)
        tags = client.list_tags(ResourceArn=resources[0]["Arn"])["Tags"]
        self.assertEqual(
            {t['Key']: t['Value'] for t in resources[0]['Tags']},
            {'Role': 'Dev'})
        self.assertEqual(
            tags,
            {'Env': 'Dev'})
