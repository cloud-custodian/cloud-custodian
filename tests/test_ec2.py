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
from c7n import tags, utils

from .common import BaseTest


class TestTagAugmentation(BaseTest):

    def test_tag_augment_empty(self):
        session_factory = self.replay_flight_data(
            'test_ec2_augment_tag_empty')
        # recording was modified to be sans tags
        ec2 = session_factory().client('ec2')
        policy = self.load_policy({
            'name': 'ec2-tags',
            'resource': 'ec2'},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 0)

    def test_tag_augment(self):
        session_factory = self.replay_flight_data(
            'test_ec2_augment_tags')
        # recording was modified to be sans tags
        ec2 = session_factory().client('ec2')
        policy = self.load_policy({
            'name': 'ec2-tags',
            'resource': 'ec2',
            'filters': [
                {'tag:Env': 'Production'}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestMetricFilter(BaseTest):

    def test_metric_filter(self):
        session_factory = self.replay_flight_data(
            'test_ec2_metric')
        ec2 = session_factory().client('ec2')
        policy = self.load_policy({
            'name': 'ec2-utilization',
            'resource': 'ec2',
            'filters': [
                {'type': 'metrics',
                 'name': 'CPUUtilization',
                 'days': 3,
                 'value': 1.5}
            ]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestTagTrim(BaseTest):

    def test_ec2_tag_trim(self):
        self.patch(tags.TagTrim, 'max_tag_count', 10)
        session_factory = self.replay_flight_data(
            'test_ec2_tag_trim')
        ec2 = session_factory().client('ec2')
        start_tags = {
            t['Key']: t['Value'] for t in
            ec2.describe_tags(
                Filters=[{'Name': 'resource-id',
                          'Values': ['i-fdb01920']}])['Tags']}
        policy = self.load_policy({
            'name': 'ec2-tag-trim',
            'resource': 'ec2',
            'filters': [
                {'type': 'tag-count', 'count': 10}],
            'actions': [
                {'type': 'tag-trim',
                 'space': 1,
                 'preserve': [
                     'Name',
                     'Env',
                     'Account',
                     'Platform',
                     'Classification',
                     'Planet'
                     ]}
                ]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        end_tags = {
            t['Key']: t['Value'] for t in
            ec2.describe_tags(
                Filters=[{'Name': 'resource-id',
                          'Values': ['i-fdb01920']}])['Tags']}

        self.assertEqual(len(start_tags)-1, len(end_tags))
        self.assertTrue('Containers' in start_tags)
        self.assertFalse('Containers' in end_tags)


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


class TestResizeInstance(BaseTest):

    def test_ec2_resize(self):
        # preconditions - three instances (2 m4.4xlarge, 1 m4.1xlarge)
        # one of the instances stopped
        session_factory = self.replay_flight_data('test_ec2_resize')
        policy = self.load_policy({
            'name': 'ec2-resize',
            'resource': 'ec2',
            'filters': [
                {'type': 'value',
                 'key': 'State.Name',
                 'value': ['running', 'stopped'],
                 'op': 'in'},
                {'type': 'value',
                 'key': 'InstanceType',
                 'value': ['m4.2xlarge', 'm4.4xlarge'],
                 'op': 'in'},
                ],
            'actions': [
                {'type': 'resize',
                 'restart': True,
                 'default': 'm4.large',
                 'type-map': {
                     'm4.4xlarge': 'm4.2xlarge'}}]
            }, session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 3)

        stopped, running = [], []
        for i in resources:
            if i['State']['Name'] == 'running':
                running.append(i['InstanceId'])
            if i['State']['Name'] == 'stopped':
                stopped.append(i['InstanceId'])

        instances = utils.query_instances(
            session_factory(),
            InstanceIds=[r['InstanceId'] for r in resources])

        cur_stopped, cur_running = [], []
        for i in instances:
            if i['State']['Name'] == 'running':
                cur_running.append(i['InstanceId'])
            if i['State']['Name'] == 'stopped':
                cur_stopped.append(i['InstanceId'])

        cur_running.sort()
        running.sort()

        self.assertEqual(cur_stopped, stopped)
        self.assertEqual(cur_running, running)
        instance_types = [i['InstanceType'] for i in instances]
        instance_types.sort()
        self.assertEqual(
            instance_types,
            list(sorted(['m4.large', 'm4.2xlarge', 'm4.2xlarge'])))


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


class TestStart(BaseTest):

    def test_ec2_start(self):
        session_factory = self.replay_flight_data(
            'test_ec2_start')
        policy = self.load_policy({
            'name': 'ec2-test-start',
            'resource': 'ec2',
            'filters': [],
            'actions': [
                {'type': 'start'}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 2)


class TestOr(BaseTest):

    def test_ec2_or_condition(self):
        session_factory = self.replay_flight_data(
            'test_ec2_stop')
        policy = self.load_policy({
            'name': 'ec2-test-snapshot',
            'resource': 'ec2',
            'filters': [
                {"or": [
                    {"tag:Name": "CompileLambda"},
                    {"tag:Name": "Spinnaker"}]}]
        }, session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            sorted([r['InstanceId'] for r in resources]),
            [u'i-13413bd7', u'i-1aebf7c0'])


class TestSnapshot(BaseTest):

    def test_ec2_snapshot_no_copy_tags(self):
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

    def test_ec2_snapshot_copy_tags(self):
        session_factory = self.replay_flight_data(
            'test_ec2_snapshot')
        policy = self.load_policy({
            'name': 'ec2-test-snapshot',
            'resource': 'ec2',
            'filters': [
                {'tag:Name': 'CompileLambda'}],
            'actions': [
                {'type': 'snapshot', 'copy-tags': ['ASV' 'Testing123']}]},
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


class TestDefaultVpc(BaseTest):

    def test_ec2_default_vpc(self):
        session_factory = self.replay_flight_data('test_ec2_default_vpc')
        p = self.load_policy(
            {'name': 'ec2-default-filters',
             'resource': 'ec2',
             'filters': [
                 {'type': 'default-vpc'}]},
            config={'region': 'us-west-2'},
            session_factory=session_factory)

        resources = p.run()
        # import pdb; pdb.set_trace()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['InstanceId'], 'i-0bfe468063b02d018')


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
