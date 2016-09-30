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
from common import BaseTest
from HTMLParser import tagfind


class TestRedshift(BaseTest):

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
        p = self.load_policy({
            'name': 'redshift-snapshot',
            'resource': 'redshift',
            'filters': [
                {'ClusterIdentifier': 'aaa'}],
            'actions': [
                {'type': 'snapshot'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)


class TestRedshiftSnapshot(BaseTest):

    def test_redshift_snapshot_simple(self):
        session_factory = self.replay_flight_data('test_redshift_snapshot_simple')
        p = self.load_policy({
            'name': 'redshift-snapshot-simple',
            'resource': 'redshift-snapshot'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_redshift_snapshot_simple_filter(self):
        session_factory = self.replay_flight_data('test_redshift_snapshot_simple')
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
