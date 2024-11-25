# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

from .common import BaseTest, load_data
from c7n.utils import jmespath_search


class KafkaTest(BaseTest):

    def test_tag_normalize(self):
        p = self.load_policy({'name': 'kafka', 'resource': 'aws.kafka'})
        resource = load_data('kafka.json')
        results = p.resource_manager.augment([resource])
        self.assertEqual(
            results[0]['Tags'],
            [{'Key': 'ResourceContact', 'Value': 'ouremailaddress@company.com'}])

    def test_subnet_filter(self):
        factory = self.replay_flight_data('test_kafka_subnet_filter')
        p = self.load_policy({
            'name': 'kafka',
            'resource': 'aws.kafka',
            'filters': [
                {'type': 'subnet',
                 'key': 'tag:NetworkLocation',
                 'value': 'Public'}]},
            session_factory=factory,
            config={'region': 'ap-northeast-2'})
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_subnet_filter_provisioned_serverless(self):
        factory = self.replay_flight_data('test_kafka_subnet_filter_provisioned_serverless')
        p = self.load_policy({
            'name': 'kafka',
            'resource': 'aws.kafka',
            'filters': [
                {'type': 'subnet',
                 'key': 'AvailabilityZone',
                 'value': 'us-east-1b'}]},
            session_factory=factory,)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['ClusterType'], 'PROVISIONED')
        self.assertEqual(resources[0]['c7n:matched-subnets'], ['subnet-08f5a2e4c12adf737'])

        self.assertEqual(resources[1]['ClusterType'], 'SERVERLESS')
        self.assertEqual(resources[1]['c7n:matched-subnets'], ['subnet-08f5a2e4c12adf737'])

    def test_kafka_tag(self):
        factory = self.replay_flight_data('test_kafka_tag')
        p = self.load_policy({
            'name': 'kafka',
            'resource': 'aws.kafka',
            'filters': [
                {'tag:App': 'absent'},
                {'tag:Env': 'Dev'}],
            'actions': [
                {'type': 'tag',
                 'tags': {'App': 'Custodian'}},
                {'type': 'remove-tag',
                 'tags': ['Env']}]},
            session_factory=factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['ClusterName'] == 'demo-cluster-1'
        client = factory().client('kafka', region_name='ap-northeast-2')
        assert client.list_tags_for_resource(
            ResourceArn=resources[0]['ClusterArn'])['Tags'] == {
                'App': 'Custodian'}

    def test_set_monitoring(self):
        factory = self.replay_flight_data('test_kafka_set_monitoring')
        p = self.load_policy({
            'name': 'kafka',
            'resource': 'aws.kafka',
            'filters': [
                {'tag:App': 'Custodian'},
                {'State': 'ACTIVE'},
                {'EnhancedMonitoring': 'DEFAULT'},
            ],
            'actions': [
                {'type': 'set-monitoring',
                 'config': {
                     'EnhancedMonitoring': 'PER_BROKER',
                     'OpenMonitoring': {
                         'Prometheus': {
                             'JmxExporter': {
                                 'EnabledInBroker': True}}}}}]},
            session_factory=factory,
            config={'region': 'ap-northeast-2'})
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['ClusterName'] == 'demo-cluster-1'
        if self.recording:
            time.sleep(5)

        info = factory().client('kafka', region_name='ap-northeast-2').describe_cluster(
            ClusterArn=resources[0]['ClusterArn'])['ClusterInfo']

        assert info['State'] == 'UPDATING'

    def test_delete(self):
        factory = self.replay_flight_data('test_kafka_delete')
        p = self.load_policy({
            'name': 'kafka',
            'resource': 'aws.kafka',
            'filters': [
                {'ClusterName': 'demo-cluster-1'}],
            'actions': [
                {'type': 'delete'},
            ]},
            session_factory=factory,
            config={'region': 'ap-northeast-2'})
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(5)

        client = factory().client('kafka', region_name='ap-northeast-2')
        cluster = client.describe_cluster(ClusterArn=resources[0]['ClusterArn']).get('ClusterInfo')
        self.assertEqual(cluster['State'], 'DELETING')

    def test_kafka_cluster_kms_filter(self):
        session_factory = self.replay_flight_data('test_kafka_cluster_kms_filter')
        kms = session_factory().client('kms', region_name='ap-northeast-2')
        expression = 'Provisioned.EncryptionInfo.EncryptionAtRest.DataVolumeKMSKeyId'
        p = self.load_policy(
            {
                'name': 'kafka-kms-filter',
                'resource': 'kafka',
                'filters': [
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/aws/kafka'
                    }
                ]
            },
            session_factory=session_factory,
            config={'region': 'ap-northeast-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=(jmespath_search(expression, resources[0])))
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/aws/kafka')

    def test_kafka_cluster_provisioned_and_serverless(self):
        session_factory = self.replay_flight_data(
            'test_kafka_cluster_provisioned_and_serverless')
        p = self.load_policy(
            {
                'name': 'kafka-kms-filter',
                'resource': 'kafka',
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['ClusterType'], 'PROVISIONED')
        self.assertEqual(resources[1]['ClusterType'], 'SERVERLESS')


class TestKafkaClusterConfiguration(BaseTest):
    def test_kafka_configuration_delete(self):
        session_factory = self.replay_flight_data("test_kafka_configuration_delete")
        p = self.load_policy(
            {
                "name": "kafka-configuration-delete",
                "resource": "kafka-config",
                "filters": [{"Arn": "arn:aws:kafka:us-east-1:761002975749:configuration/foo-config/dfc47fc4-9959-40ae-ae72-f128900f33aa-7"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("kafka")
        cluster_configrations = client.list_configurations()
        self.assertFalse("arn:aws:kafka:us-east-1:761002975749:configuration/foo-config/dfc47fc4-9959-40ae-ae72-f128900f33aa-7" in [t.get("Arn")
            for t in cluster_configrations.get("Configurations", [])])