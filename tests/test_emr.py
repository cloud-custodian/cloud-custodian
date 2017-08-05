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

import unittest

from c7n.resources import emr
from c7n.resources.emr import actions, QueryFilter

from .common import BaseTest, Bag, Config


class TestEMR(BaseTest):

    def test_get_emr_by_ids(self):
        session_factory = self.replay_flight_data(
            'test_emr_query_ids')

        ctx = Bag(
            session_factory=session_factory,
            log_dir='',
            options=Config.empty())

        mgr = emr.EMRCluster(ctx, {})
        resources = mgr.get_resources(["j-1EJMJNTXC63JW"])
        self.assertEqual(resources[0]['Id'], "j-1EJMJNTXC63JW")

    def test_consolidate_query_filter(self):
        session_factory = self.replay_flight_data(
            'test_emr_query_ids')

        ctx = Bag(
            session_factory=session_factory,
            log_dir='',
            options=Config.empty())

        query = {
            'query': [
                {'tag:foo': 'val1'},
                {'tag:foo': 'val2'},
                {'tag:bar': 'val3'}
            ]
        }
        mgr = emr.EMRCluster(ctx, query)
        self.assertEqual(
            mgr.consolidate_query_filter(),
            [
                {'Values': ['val1', 'val2'], 'Name': 'tag:foo'},
                {'Values': ['val3'], 'Name': 'tag:bar'},
                # default query
                {
                    'Values': ['WAITING', 'RUNNING', 'BOOTSTRAPPING'],
                    'Name': 'ClusterStates',
                },
            ]
        )

        query = {
            'query': [
                {'tag:foo': 'val1'},
                {'tag:foo': 'val2'},
                {'tag:bar': 'val3'},
                {'ClusterStates': 'terminated'},
            ]
        }
        mgr = emr.EMRCluster(ctx, query)
        self.assertEqual(
            mgr.consolidate_query_filter(),
            [
                {'Values': ['val1', 'val2'], 'Name': 'tag:foo'},
                {'Values': ['val3'], 'Name': 'tag:bar'},
                # verify default is overridden
                {
                    'Values': ['terminated'],
                    'Name': 'ClusterStates',
                },
            ]
        )

    def test_get_emr_tags(self):
        session_factory = self.replay_flight_data(
            'test_get_emr_tags')

        policy = self.load_policy({
            'name': 'test-get-emr-tags',
            'resource': 'emr',
            'filters': [{
                "tag:first_tag": 'first'}]},
            config={'region': 'us-west-2'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        cluster = session_factory().client(
            'emr').describe_cluster(ClusterId='j-1U3KBYP5TY79M')
        cluster_tags = cluster['Cluster']['Tags']
        tags = {t['Key']: t['Value'] for t in cluster_tags}
        self.assertEqual(tags['first_tag'], 'first')

    def test_emr_mark(self):
        session_factory = self.replay_flight_data(
            'test_emr_mark')
        p = self.load_policy({
            'name': 'emr-mark',
            'resource': 'emr',
            'filters': [
                {"tag:first_tag": 'first'}],
            'actions': [
                {'type': 'mark-for-op', 'days': 4,
                'op': 'terminate', 'tag': 'test_tag'}]},
            session_factory=session_factory)
        resources = p.run()
        new_tags = resources[0]['Tags']
        self.assertEqual(len(resources), 1)
        tag_map = {t['Key']: t['Value'] for t in new_tags}
        self.assertTrue('test_tag' in tag_map)

    def test_emr_tag(self):
        session_factory = self.replay_flight_data('test_emr_tag')
        p = self.load_policy({
                'name': 'emr-tag-table',
                'resource': 'emr',
                'filters': [{'tag:first_tag': 'first'}],
                'actions': [{
                    'type': 'tag',
                    'tags': {'new_tag_key': 'new_tag_value'}
                }]
            },
            session_factory=session_factory)
        resources = p.run()
        new_tags = resources[0]['Tags']
        tag_map = {t['Key']: t['Value'] for t in new_tags}
        self.assertEqual({
                'first_tag': 'first',
                'second_tag': 'second',
                'new_tag_key': 'new_tag_value'
            },
            tag_map)

    def test_emr_unmark(self):
        session_factory = self.replay_flight_data(
            'test_emr_unmark')
        p = self.load_policy({
            'name': 'emr-unmark',
            'resource': 'emr',
            'filters': [
                {"tag:first_tag": 'first'}],
            'actions': [
                {'type': 'remove-tag',
                 'tags': ['test_tag']}]},
            session_factory=session_factory)
        resources = p.run()
        old_tags = resources[0]['Tags']
        self.assertEqual(len(resources), 1)
        self.assertFalse('test_tag' in old_tags)


class TestEMRQueryFilter(unittest.TestCase):

    def test_parse(self):
        self.assertEqual(QueryFilter.parse([]), [])
        x = QueryFilter.parse(
            [{'ClusterStates': 'terminated'}])
        self.assertEqual(
            x[0].query(),
            {'Name': 'ClusterStates', 'Values': ['terminated']})

        # Test consolidation of multiple values for query
        self.assertEqual(QueryFilter.parse([]), [])
        x = QueryFilter.parse(
            [{'ClusterStates': 'terminated'},
             {'ClusterStates': 'running'},
             {'ClusterStates': 'waiting'}])
        self.assertEqual(
            x[0].query(),
            {'Name': 'ClusterStates', 'Values': ['terminated']})
        self.assertEqual(
            x[1].query(),
            {'Name': 'ClusterStates', 'Values': ['running']})
        self.assertEqual(
            x[2].query(),
            {'Name': 'ClusterStates', 'Values': ['waiting']})

        self.assertEqual(QueryFilter.parse([]), [])
        x = QueryFilter.parse(
            [{'CreatedBefore': 1470968567.05}])
        self.assertEqual(
            x[0].query(),
            {'Name': 'CreatedBefore', 'Values': 1470968567.05})

        self.assertEqual(QueryFilter.parse([]), [])
        x = QueryFilter.parse(
            [{'CreatedAfter': 1470974021.557}])
        self.assertEqual(
            x[0].query(),
            {'Name': 'CreatedAfter', 'Values': 1470974021.557})

        self.assertTrue(
            isinstance(
                QueryFilter.parse(
                    [{'tag:ASV': 'REALTIMEMSG'}])[0],
                QueryFilter))

        self.assertRaises(
            ValueError,
            QueryFilter.parse,
            [{'tag:ASV': None}])

        self.assertRaises(
            ValueError,
            QueryFilter.parse,
            [{'foo': 'bar'}])

        self.assertRaises(
            ValueError,
            QueryFilter.parse,
            [{'too': 'many', 'keys': 'error'}])

        self.assertRaises(
            ValueError,
            QueryFilter.parse,
            ['Not a dictionary'])


class TestTerminate(BaseTest):

    def test_emr_terminate(self):
        session_factory = self.replay_flight_data(
            'test_emr_terminate')
        policy = self.load_policy({
            'name': 'emr-test-terminate',
            'resource': 'emr',
            'actions': [
                {'type': 'terminate'}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestActions(unittest.TestCase):

    def test_action_construction(self):

        self.assertIsInstance(
            actions.factory('terminate', None),
            emr.Terminate)
