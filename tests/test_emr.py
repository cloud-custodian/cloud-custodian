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
import unittest

from c7n.resources import emr
from c7n.resources.emr import actions, QueryFilter
from c7n import tags, utils

from .common import BaseTest


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
