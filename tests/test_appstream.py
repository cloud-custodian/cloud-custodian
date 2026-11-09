# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class AppStreamTest(BaseTest):

    def test_appstream_fleet_query(self):
        """Record: one fleet named c7n-test-fleet tagged Owner=c7n."""
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
        """Record: one stack named c7n-test-stack tagged Owner=c7n."""
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
        """Record: one image builder named c7n-test-image-builder tagged Owner=c7n."""
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
        """Record: one private image named c7n-test-image tagged Owner=c7n."""
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

    def test_appstream_image_tag(self):
        """Record: one private image named c7n-test-image without an Env tag."""
        factory = self.replay_flight_data('test_appstream_image_tag')
        p = self.load_policy({
            'name': 'appstream-image-tag',
            'resource': 'aws.appstream-image',
            'filters': [{'Name': 'c7n-test-image'}, {'tag:Env': 'absent'}],
            'actions': [{'type': 'tag', 'key': 'Env', 'value': 'dev'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('appstream')
        tags = client.list_tags_for_resource(ResourceArn=resources[0]['Arn'])['Tags']
        self.assertEqual(tags.get('Env'), 'dev')

    def test_appstream_app_block_builder_query(self):
        """Record: one app block builder named c7n-test-abb tagged Owner=c7n."""
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
        """Record: one app block named c7n-test-app-block tagged Owner=c7n."""
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
        """Record: one application named c7n-test-app tagged Owner=c7n."""
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
        """Record: one enabled user pool user c7n-test@example.com."""
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
        """Record: one fleet in a subnet with MapPublicIpOnLaunch false."""
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
        """Record: one fleet using a security group named c7n-appstream."""
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
        """Record: one fleet tagged NetworkLocation=private whose security
        group is also tagged NetworkLocation=private."""
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
        """Record: one image builder in a subnet with MapPublicIpOnLaunch false
        using a security group named c7n-appstream."""
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
        """Record: one app block builder in a subnet with MapPublicIpOnLaunch
        false using a security group named c7n-appstream."""
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
        """Record: two private images; c7n-test-image shared with an external
        account, c7n-test-image-2 not shared."""
        factory = self.replay_flight_data('test_appstream_image_cross_account')
        p = self.load_policy({
            'name': 'appstream-image-cross-account',
            'resource': 'aws.appstream-image',
            'filters': [{'type': 'cross-account'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'c7n-test-image')
        self.assertEqual(len(resources[0]['c7n:CrossAccountViolations']), 1)
