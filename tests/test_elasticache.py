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

from tests.common import BaseTest


class TestElastiCacheCluster(BaseTest):

    def test_elasticache_cluster_simple(self):
        session_factory = self.replay_flight_data('test_elasticache_cluster_simple')
        p = self.load_policy({
            'name': 'elasticache-cluster-simple',
            'resource': 'cache-cluster'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 4)

    def test_elasticache_cluster_simple_filter(self):
        session_factory = self.replay_flight_data('test_elasticache_cluster_simple')
        p = self.load_policy({
            'name': 'elasticache-cluster-simple-filter',
            'resource': 'cache-cluster',
            'filters': [
                {'type': 'value',
                 'key': 'Engine',
                 'value': 'memcached'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_elasticache_cluster_delete(self):
        session_factory = self.replay_flight_data('test_elasticache_cluster_delete')
        p = self.load_policy({
            'name': 'elasticache-cluster-delete',
            'resource': 'cache-cluster',
            'filters': [
                {'type': 'value',
                 'key': 'Engine',
                 'value': 'memcached'}],
            'actions': [
                {'type': 'delete'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_elasticache_cluster_snapshot(self):
        session_factory = self.replay_flight_data('test_elasticache_cluster_snapshot')
        p = self.load_policy({
            'name': 'elasticache-cluster-snapshot',
            'resource': 'cache-cluster',
            'actions': [{'type': 'snapshot'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 4)


class TestElastiCacheSubnetGroup(BaseTest):

    def test_elasticache_subnet_group(self):
        session_factory = self.replay_flight_data('test_elasticache_subnet_group')
        p = self.load_policy({
            'name': 'elasticache-subnet-group',
            'resource': 'cache-subnet-group'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)


class TestElastiCacheSnapshot(BaseTest):

    def test_elasticache_snapshot(self):
        session_factory = self.replay_flight_data('test_elasticache_snapshot')
        p = self.load_policy({
            'name': 'elasticache-snapshot',
            'resource': 'cache-snapshot'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_elasticache_snapshot_age_filter(self):
        factory = self.replay_flight_data('test_elasticache_snapshot')
        p = self.load_policy({
            'name': 'elasticache-snapshot-age-filter',
            'resource': 'cache-snapshot',
            'filters': [{'type': 'age', 'days': 2}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_elasticache_snapshot_delete(self):
        factory = self.replay_flight_data('test_elasticache_snapshot_delete')
        p = self.load_policy({
            'name': 'elasticache-snapshot-delete',
            'resource': 'cache-snapshot',
            'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 3)