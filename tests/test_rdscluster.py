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


class RDSClusterTest(BaseTest):

    def test_rdscluster_security_group(self):
        session_factory = self.replay_flight_data('test_rdscluster_sg_filter')
        p = self.load_policy({
            'name': 'rdscluster-sg',
            'resource': 'rds-cluster',
            'filters': [
                {'type': 'security-group',
                 'key': 'GroupName',
                 'value': 'default'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DatabaseName'], 'devtest')

    def test_rdscluster_subnet(self):
        session_factory = self.replay_flight_data('test_rdscluster_subnet')
        p = self.load_policy({
            'name': 'rdscluster-sub',
            'resource': 'rds-cluster',
            'filters': [
                {'type': 'subnet',
                 'key': 'MapPublicIpOnLaunch',
                 'value': True}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DatabaseName'], 'devtest')

    def test_rdscluster_simple(self):
        session_factory = self.replay_flight_data('test_rdscluster_simple')
        p = self.load_policy({
            'name': 'rdscluster-simple',
            'resource': 'rds-cluster'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_rdscluster_simple_filter(self):
        session_factory = self.replay_flight_data('test_rdscluster_simple')
        p = self.load_policy({
            'name': 'rdscluster-simple-filter',
            'resource': 'rds-cluster',
            'filters': [
                {'type': 'value',
                 'key': 'DBClusterIdentifier',
                 'value': 'bbb'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_delete(self):
        session_factory = self.replay_flight_data('test_rdscluster_delete')
        p = self.load_policy({
            'name': 'rdscluster-delete',
            'resource': 'rds-cluster',
            'filters': [
                {'type': 'value',
                 'key': 'DBClusterIdentifier',
                 'value': 'bbb'}],
            'actions': [
                {'type': 'delete',
                 'delete-instances': False}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_delete_with_instances(self):
        session_factory = self.replay_flight_data('test_rdscluster_delete_with_instances')
        p = self.load_policy({
            'name': 'rdscluster-delete',
            'resource': 'rds-cluster',
            'filters': [
                {'type': 'value',
                 'key': 'DBClusterIdentifier',
                 'value': 'bbb'}],
            'actions': [
                {'type': 'delete',
                 'delete-instances': True}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_retention(self):
        session_factory = self.replay_flight_data('test_rdscluster_retention')
        p = self.load_policy({
            'name': 'rdscluster-delete',
            'resource': 'rds-cluster',
            'filters': [
                {'type': 'value',
                 'key': 'DBClusterIdentifier',
                 'value': 'bbb'}],
            'actions': [{'type': 'retention', 'days': 21}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_snapshot(self):
        session_factory = self.replay_flight_data('test_rdscluster_snapshot')
        p = self.load_policy({
            'name': 'rdscluster-snapshot',
            'resource': 'rds-cluster',
            'filters': [
                {'type': 'value',
                 'key': 'DBClusterIdentifier',
                 'value': 'bbb'}],
            'actions': [{'type': 'snapshot'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)


class RDSClusterSnapshotTest(BaseTest):

    def test_rdscluster_snapshot_simple(self):
        session_factory = self.replay_flight_data(
            'test_rdscluster_snapshot_simple')
        p = self.load_policy({
            'name': 'rdscluster-snapshot-simple',
            'resource': 'rds-cluster-snapshot'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_rdscluster_snapshot_simple_filter(self):
        session_factory = self.replay_flight_data(
            'test_rdscluster_snapshot_simple')
        p = self.load_policy({
            'name': 'rdscluster-snapshot-simple-filter',
            'resource': 'rds-cluster-snapshot',
            'filters': [
                {'type': 'value',
                 'key': 'StorageEncrypted',
                 'value': False}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rdscluster_snapshot_age_filter(self):
        factory = self.replay_flight_data('test_rdscluster_snapshot_simple')
        p = self.load_policy({
            'name': 'rdscluster-snapshot-age-filter',
            'resource': 'rds-cluster-snapshot',
            'filters': [{'type': 'age', 'days': 7}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_rdscluster_snapshot_trim(self):
        factory = self.replay_flight_data('test_rdscluster_snapshot_delete')
        p = self.load_policy({
            'name': 'rdscluster-snapshot-trim',
            'resource': 'rds-cluster-snapshot',
            'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
