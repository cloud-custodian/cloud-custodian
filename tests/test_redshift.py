# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from .common import BaseTest


class TestRedshift(BaseTest):

    def test_redshift_security_group_filter(self):
        factory = self.replay_flight_data(
            'test_redshift_security_group_filter')
        p = self.load_policy({
            'name': 'redshift-query',
            'resource': 'redshift',
            'filters': [
                {'type': 'security-group',
                 'key': 'GroupName',
                 'value': 'default'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ClusterIdentifier'], 'dev-test')

    def test_redshift_subnet_filter(self):
        factory = self.replay_flight_data('test_redshift_subnet_filter')
        p = self.load_policy({
            'name': 'redshift-query',
            'resource': 'redshift',
            'filters': [
                {'type': 'subnet',
                 'key': 'MapPublicIpOnLaunch',
                 'value': True}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ClusterIdentifier'], 'dev-test')

    def test_redshift_query(self):
        factory = self.replay_flight_data('test_redshift_query')
        p = self.load_policy({
            'name': 'redshift-query',
            'resource': 'redshift'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(resources, [])

    def test_redshift_parameter(self):
        factory = self.replay_flight_data('test_redshift_parameter')
        p = self.load_policy({
            'name': 'redshift-ssl',
            'resource': 'redshift',
            'filters': [
                {'type': 'param',
                 'key': 'require_ssl',
                 'value': False}]},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_simple_tag_filter(self):
        factory = self.replay_flight_data('test_redshift_tag_filter')
        client = factory().client('redshift')
        p = self.load_policy({
            'name': 'redshift-tag-filter',
            'resource': 'redshift',
            'filters': [
                {'tag:maid_status': 'not-null'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(
            resources[0]['ClusterIdentifier'])
        tags = client.describe_tags(ResourceName=arn)['TaggedResources']
        tag_map = {t['Tag']['Key'] for t in tags}
        self.assertTrue('maid_status' in tag_map)

    def test_redshift_cluster_mark(self):
        factory = self.replay_flight_data('test_redshift_cluster_mark')
        client = factory().client('redshift')
        p = self.load_policy({
            'name': 'redshift-cluster-mark',
            'resource': 'redshift',
            'filters': [
                {'type': 'value',
                 'key': 'ClusterIdentifier',
                 'value': 'c7n'}],
            'actions': [
                {'type': 'mark-for-op', 'days': 30,
                 'op': 'delete'}]},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(
            resources[0]['ClusterIdentifier'])
        tags = client.describe_tags(ResourceName=arn)['TaggedResources']
        tag_map = {t['Tag']['Key'] for t in tags}
        self.assertTrue('maid_status' in tag_map)

    def test_redshift_cluster_unmark(self):
        factory = self.replay_flight_data('test_redshift_cluster_unmark')
        client = factory().client('redshift')
        p = self.load_policy({
            'name': 'redshift-cluster-unmark',
            'resource': 'redshift',
            'filters': [
                {'type': 'value',
                 'key': 'ClusterIdentifier',
                 'value': 'c7n'}],
            'actions': [
                {'type': 'unmark'}]},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(
            resources[0]['ClusterIdentifier'])
        tags = client.describe_tags(ResourceName=arn)['TaggedResources']
        tag_map = {t['Tag']['Key'] for t in tags}
        self.assertFalse('maid_status' in tag_map)

    def test_redshift_delete(self):
        factory = self.replay_flight_data('test_redshift_delete')
        p = self.load_policy({
            'name': 'redshift-ssl',
            'resource': 'redshift',
            'filters': [
                {'ClusterIdentifier': 'c7n-test'}],
            'actions': [
                {'type': 'delete', 'skip-snapshot': True}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_default_vpc(self):
        session_factory = self.replay_flight_data('test_redshift_default_vpc')
        p = self.load_policy(
            {'name': 'redshift-default-filters',
             'resource': 'redshift',
             'filters': [
                 {'type': 'default-vpc'}]},
            config={'region': 'us-west-2'},
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_retention(self):
        session_factory = self.replay_flight_data('test_redshift_retention')
        p = self.load_policy({
            'name': 'redshift-retention',
            'resource': 'redshift',
            'filters': [
                {'type': 'value',
                 'key': 'ClusterIdentifier',
                 'value': 'aaa'}],
            'actions': [{'type': 'retention', 'days': 21}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_snapshot(self):
        factory = self.replay_flight_data('test_redshift_snapshot')
        client = factory().client('redshift')
        cluster_tags = []
        p = self.load_policy({
            'name': 'redshift-snapshot',
            'resource': 'redshift',
            'filters': [
                {'type': 'value',
                 'key': 'ClusterIdentifier',
                 'value': 'test-cluster',
                 'op': 'eq'}],
            'actions': [
                {'type': 'snapshot'}]},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        cluster = client.describe_clusters(
            ClusterIdentifier=resources[0]['ClusterIdentifier'])
        id_cluster = cluster.get('Clusters')[0].get('ClusterIdentifier')
        snapshot = client.describe_cluster_snapshots(
            SnapshotIdentifier='backup-test-cluster-2017-01-12')
        get_snapshots = snapshot.get('Snapshots')
        id_snapshot = get_snapshots[0].get('ClusterIdentifier')
        tag_snapshot = get_snapshots[0].get('Tags')
        self.assertEqual(id_cluster, id_snapshot)
        arn = p.resource_manager.generate_arn(
            resources[0]['ClusterIdentifier'])
        cluster_tags_array = client.describe_tags(ResourceName=arn)['TaggedResources']
        for cluster_tag_elem in cluster_tags_array:
            cluster_tags.append(cluster_tag_elem['Tag'])
        self.assertEqual(cluster_tags, tag_snapshot)

    def test_redshift_vpc_routing(self):
        factory = self.replay_flight_data('test_redshift_vpc_routing')
        client = factory().client('redshift')
        p = self.load_policy({
            'name': 'redshift-vpc-routing',
            'resource': 'redshift',
            'filters': [
                {'type': 'value',
                 'key': 'EnhancedVpcRouting',
                 'value': True}],
            'actions': [{'type': 'enable-vpc-routing', 'value': False}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        # Ensure that the cluster starts to modify EnhancedVpcRouting value.
        response = client.describe_clusters(
            ClusterIdentifier=resources[0]['ClusterIdentifier'])
        cluster = response['Clusters'][0]
        self.assertEquals(
            cluster['ClusterIdentifier'], resources[0]['ClusterIdentifier'])
        self.assertEquals(
            cluster['ClusterStatus'], 'modifying')
        self.assertTrue(
            cluster['PendingModifiedValues']['EnhancedVpcRouting'])


class TestRedshiftSnapshot(BaseTest):

    def test_redshift_snapshot_simple(self):
        session_factory = self.replay_flight_data(
            'test_redshift_snapshot_simple')
        p = self.load_policy({
            'name': 'redshift-snapshot-simple',
            'resource': 'redshift-snapshot'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_redshift_snapshot_simple_filter(self):
        session_factory = self.replay_flight_data(
            'test_redshift_snapshot_simple')
        p = self.load_policy({
            'name': 'redshift-snapshot-simple-filter',
            'resource': 'redshift-snapshot',
            'filters': [
                {'type': 'value',
                 'key': 'Encrypted',
                 'value': False}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_redshift_snapshot_age_filter(self):
        factory = self.replay_flight_data('test_redshift_snapshot_simple')
        p = self.load_policy({
            'name': 'redshift-snapshot-age-filter',
            'resource': 'redshift-snapshot',
            'filters': [{'type': 'age', 'days': 7}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_redshift_snapshot_delete(self):
        factory = self.replay_flight_data('test_redshift_snapshot_delete')
        p = self.load_policy({
            'name': 'redshift-snapshot-delete',
            'resource': 'redshift-snapshot',
            'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_redshift_snapshot_mark(self):
        factory = self.replay_flight_data('test_redshift_snapshot_mark')
        client = factory().client('redshift')
        p = self.load_policy({
            'name': 'redshift-snapshot-mark',
            'resource': 'redshift-snapshot',
            'filters': [
                {'type': 'value',
                 'key': 'SnapshotIdentifier',
                 'value': 'c7n-snapshot'}],
            'actions': [
                {'type': 'mark-for-op', 'days': 30,
                 'op': 'delete'}]},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(
            resources[0]['SnapshotIdentifier'])
        tags = client.describe_tags(ResourceName=arn)['TaggedResources']
        tag_map = {t['Tag']['Key'] for t in tags}
        self.assertTrue('maid_status' in tag_map)

    def test_redshift_snapshot_unmark(self):
        factory = self.replay_flight_data('test_redshift_snapshot_unmark')
        client = factory().client('redshift')
        p = self.load_policy({
            'name': 'redshift-snapshot-unmark',
            'resource': 'redshift-snapshot',
            'filters': [
                {'type': 'value',
                 'key': 'SnapshotIdentifier',
                 'value': 'c7n-snapshot'}],
            'actions': [
                {'type': 'unmark'}]},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(
            resources[0]['SnapshotIdentifier'])
        tags = client.describe_tags(ResourceName=arn)['TaggedResources']
        tag_map = {t['Tag']['Key'] for t in tags}
        self.assertFalse('maid_status' in tag_map)


class TestModifyVpcSecurityGroupsAction(BaseTest):
    def test_redshift_remove_matched_security_groups(self):
        # Test conditions:
        # - running 2 Redshift clusters in default VPC
        #    - a default security group with id 'sg-7a3fcb13' exists
        #    - security group named PROD-ONLY-Test-Security-Group exists in
        #      VPC and is attached to one of the clusters
        #        - translates to 1 cluster marked non-compliant
        #
        # Results in 2 clusters with default Security Group attached
        session_factory = self.replay_flight_data(
            'test_redshift_remove_matched_security_groups')
        p = self.load_policy(
            {'name': 'redshift-remove-matched-security-groups',
             'resource': 'redshift',
             'filters': [
                 {'type': 'security-group', 'key': 'GroupName',
                  'value': '(.*PROD-ONLY.*)', 'op': 'regex'}],
             'actions': [
                 {'type': 'modify-security-groups', 'remove': 'matched',
                  'isolation-group': 'sg-7a3fcb13'}]
             },
            session_factory=session_factory)
        clean_p = self.load_policy(
            {'name': 'redshift-verify-remove-matched-security-groups',
             'resource': 'redshift',
             'filters': [
                 {'type': 'security-group', 'key': 'GroupName',
                  'value': 'default'}]
             },
            session_factory=session_factory)

        resources = p.run()
        clean_resources = clean_p.run()

        # clusters autoscale across AZs, so they get -001, -002, etc appended
        self.assertIn('test-sg-fail', resources[0]['ClusterIdentifier'])

        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['VpcSecurityGroups']), 1)
        # show that it was indeed a replacement of security groups
        self.assertEqual(len(clean_resources[0]['VpcSecurityGroups']), 1)
        self.assertEqual(len(clean_resources), 2)

    def test_redshift_add_security_group(self):
        # Test conditions:
        #    - running 2 redshift clusters in default VPC
        #    - a default security group with id 'sg-7a3fcb13' exists
        #      attached to both clusters
        #    - security group named PROD-ONLY-Test-Security-Group exists in
        #      VPC and is attached to 1/2 clusters
        #        - translates to 1 cluster marked to get new group attached
        #
        # Results in 1 cluster with default Security Group and
        # PROD-ONLY-Test-Security-Group

        session_factory = self.replay_flight_data(
            'test_redshift_add_security_group')

        p = self.load_policy({
            'name': 'add-sg-to-prod-redshift',
            'resource': 'redshift',
            'filters': [
                {'type': 'security-group', 'key': 'GroupName',
                 'value': 'default'},
                {'type': 'value', 'key': 'ClusterIdentifier',
                 'value': 'test-sg-fail.*', 'op': 'regex'}
            ],
            'actions': [
                {'type': 'modify-security-groups', 'add': 'sg-6360920a'}
            ]
        },
            session_factory=session_factory)
        clean_p = self.load_policy({
            'name': 'validate-add-sg-to-prod-redshift',
            'resource': 'redshift',
            'filters': [
                {'type': 'security-group', 'key': 'GroupName',
                 'value': 'default'},
                {'type': 'security-group', 'key': 'GroupName',
                 'value': 'PROD-ONLY-Test-Security-Group'}
            ]
        },
            session_factory=session_factory)

        resources = p.run()
        clean_resources = clean_p.run()

        self.assertEqual(len(resources), 1)
        self.assertIn('test-sg-fail', resources[0]['ClusterIdentifier'])
        self.assertEqual(len(resources[0]['VpcSecurityGroups']), 1)
        self.assertEqual(len(clean_resources[0]['VpcSecurityGroups']), 2)
        self.assertEqual(len(clean_resources), 2)
