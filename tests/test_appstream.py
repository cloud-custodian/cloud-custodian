# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
from c7n.utils import local_session


class AppStreamTest(BaseTest):

    def test_appstream_fleet_query(self):
        factory = self.replay_flight_data('test_appstream_fleet_query')
        p = self.load_policy({
            'name': 'appstream-fleet-query',
            'resource': 'aws.appstream-fleet',
            'filters': [{'tag:Owner': 'c7n'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n-test-fleet')

    def test_appstream_stack_query(self):
        factory = self.replay_flight_data('test_appstream_stack_query')
        p = self.load_policy({
            'name': 'appstream-stack-query',
            'resource': 'aws.appstream-stack',
            'filters': [{'tag:Owner': 'c7n'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n-test-stack')

    def test_appstream_image_builder_query(self):
        factory = self.replay_flight_data('test_appstream_image_builder_query')
        p = self.load_policy({
            'name': 'appstream-image-builder-query',
            'resource': 'aws.appstream-image-builder',
            'filters': [{'tag:Owner': 'c7n'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n-test-image-builder')

    def test_appstream_image_query(self):
        factory = self.replay_flight_data('test_appstream_image_query')
        p = self.load_policy({
            'name': 'appstream-image-query',
            'resource': 'aws.appstream-image',
            'filters': [{'tag:Owner': 'c7n'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n-test-image')
        self.assertEqual(resources[0]['Visibility'], 'PRIVATE')

    def test_appstream_image_builder_tag(self):
        factory = self.replay_flight_data('test_appstream_image_builder_tag')
        sent = []
        local_session(factory).events.register(
            'before-parameter-build.resource-groups-tagging-api.TagResources',
            lambda params, **kw: sent.append(params))
        p = self.load_policy({
            'name': 'appstream-image-builder-tag',
            'resource': 'aws.appstream-image-builder',
            'filters': [{'Name': 'c7n-test-image-builder'}, {'tag:Env': 'absent'}],
            'actions': [{'type': 'tag', 'key': 'Env', 'value': 'dev'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(sent, [{
            'ResourceARNList': [resources[0]['Arn']],
            'Tags': {'Env': 'dev'}}])

    def test_appstream_app_block_builder_query(self):
        factory = self.replay_flight_data('test_appstream_app_block_builder_query')
        p = self.load_policy({
            'name': 'appstream-app-block-builder-query',
            'resource': 'aws.appstream-app-block-builder',
            'filters': [{'tag:Owner': 'c7n'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n-test-abb')

    def test_appstream_app_block_query(self):
        factory = self.replay_flight_data('test_appstream_app_block_query')
        p = self.load_policy({
            'name': 'appstream-app-block-query',
            'resource': 'aws.appstream-app-block',
            'filters': [{'tag:Owner': 'c7n'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n-test-app-block')

    def test_appstream_application_query(self):
        factory = self.replay_flight_data('test_appstream_application_query')
        p = self.load_policy({
            'name': 'appstream-application-query',
            'resource': 'aws.appstream-application',
            'filters': [{'tag:Owner': 'c7n'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n-test-app')

    def test_appstream_user_query(self):
        factory = self.replay_flight_data('test_appstream_user_query')
        p = self.load_policy({
            'name': 'appstream-user-query',
            'resource': 'aws.appstream-user',
            'filters': [{'Enabled': True}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['UserName'], 'c7n-test@example.com')
        self.assertEqual(resources[0]['AuthenticationType'], 'USERPOOL')

    def test_appstream_fleet_subnet_filter(self):
        factory = self.replay_flight_data('test_appstream_fleet_subnet_filter')
        p = self.load_policy({
            'name': 'appstream-fleet-subnet',
            'resource': 'aws.appstream-fleet',
            'filters': [{
                'type': 'subnet',
                'key': 'MapPublicIpOnLaunch',
                'value': False}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appstream_fleet_security_group_filter(self):
        factory = self.replay_flight_data('test_appstream_fleet_security_group_filter')
        p = self.load_policy({
            'name': 'appstream-fleet-sg',
            'resource': 'aws.appstream-fleet',
            'filters': [{
                'type': 'security-group',
                'key': 'GroupName',
                'value': 'c7n-appstream'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appstream_fleet_network_location(self):
        factory = self.replay_flight_data('test_appstream_fleet_network_location')
        p = self.load_policy({
            'name': 'appstream-fleet-network-location',
            'resource': 'aws.appstream-fleet',
            'filters': [{
                'type': 'network-location',
                'compare': ['resource', 'security-group'],
                'key': 'tag:NetworkLocation',
                'match': 'equal'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appstream_image_builder_network_filters(self):
        factory = self.replay_flight_data('test_appstream_image_builder_network_filters')
        p = self.load_policy({
            'name': 'appstream-image-builder-network',
            'resource': 'aws.appstream-image-builder',
            'filters': [
                {'type': 'subnet', 'key': 'MapPublicIpOnLaunch', 'value': False},
                {'type': 'security-group', 'key': 'GroupName', 'value': 'c7n-appstream'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appstream_app_block_builder_network_filters(self):
        factory = self.replay_flight_data('test_appstream_app_block_builder_network_filters')
        p = self.load_policy({
            'name': 'appstream-app-block-builder-network',
            'resource': 'aws.appstream-app-block-builder',
            'filters': [
                {'type': 'subnet', 'key': 'MapPublicIpOnLaunch', 'value': False},
                {'type': 'security-group', 'key': 'GroupName', 'value': 'c7n-appstream'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_appstream_image_cross_account(self):
        factory = self.replay_flight_data('test_appstream_image_cross_account')
        p = self.load_policy({
            'name': 'appstream-image-cross-account',
            'resource': 'aws.appstream-image',
            'filters': [{'type': 'cross-account', 'whitelist': ['111111111111']}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n-test-image')
        self.assertEqual(resources[0]['c7n:CrossAccountViolations'], ['123456789012'])
