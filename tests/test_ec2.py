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

from c7n.resources import ec2
from c7n.resources.ec2 import actions, QueryFilter
from c7n import tags

from .common import BaseTest


class TestVolumeFilter(BaseTest):

    def test_ec2_attached_ebs_filter(self):
        session_factory = self.replay_flight_data(
            'test_ec2_attached_ebs_filter')
        policy = self.load_policy({
            'name': 'ec2-unencrypted-vol',
            'resource': 'ec2',
            'filters': [
                {'type': 'ebs',
                 'key': 'Encrypted',
                 'value': False}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    # DISABLED / Re-record flight data on public account        
    def test_ec2_attached_volume_skip_block(self):
        session_factory = self.replay_flight_data(
            'test_ec2_attached_ebs_filter')
        policy = self.load_policy({
            'name': 'ec2-unencrypted-vol',
            'resource': 'ec2',
            'filters': [
                {'type': 'ebs',
                 'skip-devices': ['/dev/sda1', '/dev/xvda', '/dev/sdb1'],
                 'key': 'Encrypted',
                 'value': False}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 0)


class TestImageAgeFilter(BaseTest):

    def test_ec2_image_age(self):
        session_factory = self.replay_flight_data(
            'test_ec2_image_age_filter')
        policy = self.load_policy({
            'name': 'ec2-image-age',
            'resource': 'ec2',
            'filters': [
                {'State.Name': 'running'},
                {'type': 'image-age',
                 'days': 30}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestInstanceAge(BaseTest):

    # placebo doesn't record tz information
    def xtest_ec2_instance_age(self):
        session_factory = self.replay_flight_data(
            'test_ec2_instance_age_filter')
        policy = self.load_policy({
            'name': 'ec2-instance-age',
            'resource': 'ec2',
            'filters': [
                {'State.Name': 'running'},
                {'type': 'instance-age',
                 'days': 10}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestTag(BaseTest):

    def test_ec2_tag(self):
        session_factory = self.replay_flight_data(
            'test_ec2_mark')
        policy = self.load_policy({
            'name': 'ec2-test-mark',
            'resource': 'ec2',
            'filters': [
                {'State.Name': 'running'}],
            'actions': [
                {'type': 'tag',
                 'key': 'Testing',
                 'value': 'Testing123'}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_ec2_untag(self):
        session_factory = self.replay_flight_data(
            'test_ec2_untag')
        policy = self.load_policy({
            'name': 'ec2-test-unmark',
            'resource': 'ec2',
            'filters': [
                {'tag:Testing': 'not-null'}],
            'actions': [
                {'type': 'remove-tag',
                 'key': 'Testing'}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestStop(BaseTest):

    def test_ec2_stop(self):
        session_factory = self.replay_flight_data(
            'test_ec2_stop')
        policy = self.load_policy({
            'name': 'ec2-test-stop',
            'resource': 'ec2',
            'filters': [
                {'tag:Testing': 'not-null'}],
            'actions': [
                {'type': 'stop'}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestSnapshot(BaseTest):

    def test_ec2_snapshot(self):
        session_factory = self.replay_flight_data(
            'test_ec2_snapshot')
        policy = self.load_policy({
            'name': 'ec2-test-snapshot',
            'resource': 'ec2',
            'filters': [
                {'tag:Name': 'CompileLambda'}],
            'actions': [
                {'type': 'snapshot'}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestEC2QueryFilter(unittest.TestCase):

    def test_parse(self):
        self.assertEqual(QueryFilter.parse([]), [])
        x = QueryFilter.parse(
            [{'instance-state-name': 'running'}])
        self.assertEqual(
            x[0].query(),
            {'Name': 'instance-state-name', 'Values': ['running']})
        
        self.assertTrue(
            isinstance(
                QueryFilter.parse(
                    [{'tag:ASV': 'REALTIMEMSG'}])[0],
                QueryFilter))

        self.assertRaises(
            ValueError,
            QueryFilter.parse,
            [{'tag:ASV': None}])
        

class TestActions(unittest.TestCase):

    def test_action_construction(self):

        self.assertIsInstance(
            actions.factory('mark', None),
            tags.Tag)

        self.assertIsInstance(
            actions.factory('stop', None),
            ec2.Stop)

        self.assertIsInstance(
            actions.factory('terminate', None),
            ec2.Terminate)        

        

