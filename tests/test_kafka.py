# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

from .common import BaseTest, load_data


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
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

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
            session_factory=factory)
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['ClusterName'] == 'dev'
        client = factory().client('kafka')
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
            session_factory=factory)
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['ClusterName'] == 'dev'
        if self.recording:
            time.sleep(5)

        info = factory().client('kafka').describe_cluster(
            ClusterArn=resources[0]['ClusterArn'])['ClusterInfo']

        assert info['State'] == 'UPDATING'

    def test_delete(self):
        factory = self.replay_flight_data('test_kafka_delete')
        p = self.load_policy({
            'name': 'kafka',
            'resource': 'aws.kafka',
            'filters': [
                {'ClusterName': 'dev'}],
            'actions': [
                {'type': 'delete'},
            ]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(5)

        client = factory().client('kafka')
        cluster = client.describe_cluster(ClusterArn=resources[0]['ClusterArn']).get('ClusterInfo')
        self.assertEqual(cluster['State'], 'DELETING')
