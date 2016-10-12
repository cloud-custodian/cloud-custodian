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
from datetime import datetime, timedelta
import json
import shutil
import tempfile


from c7n import policy, manager
from c7n.resources.ec2 import EC2
from c7n.utils import dumps

from .common import BaseTest, Config


class DummyResource(manager.ResourceManager):

    def resources(self):
        return [
            {'abc': 123},
            {'def': 456}]

    @property
    def actions(self):

        class _a(object):
            def name(self):
                return self.f.__name__

            def __init__(self, f):
                self.f = f

            def process(self, resources):
                return self.f(resources)

        def p1(resources):
            return [
                {'abc': 456},
                {'def': 321}]

        def p2(resources):
            return resources

        return [_a(p1), _a(p2)]


class TestPolicy(BaseTest):

    def test_policy_name_filtering(self):

        collection = self.load_policy_set(
            {'policies': [
                {'name': 's3-remediate',
                 'resource': 's3'},
                {'name': 's3-global-grants',
                 'resource': 's3'},
                {'name': 'ec2-tag-compliance-stop',
                 'resource': 'ec2'},
                {'name': 'ec2-tag-compliance-kill',
                 'resource': 'ec2'},
                {'name': 'ec2-tag-compliance-remove',
                 'resource': 'ec2'}]},
            )
        self.assertEqual(
            [p.name for p in collection.policies('s3*')],
            ['s3-remediate', 's3-global-grants'])

        self.assertEqual(
            [p.name for p in collection.policies('ec2*')],
            ['ec2-tag-compliance-stop',
             'ec2-tag-compliance-kill',
             'ec2-tag-compliance-remove'])

    def test_file_not_found(self):
        self.assertRaises(
            ValueError, policy.load, Config.empty(), "/asdf12")

    def test_lambda_policy_metrics(self):
        session_factory = self.replay_flight_data('test_lambda_policy_metrics')
        p = self.load_policy({
            'name': 'ec2-tag-compliance-v6',
            'resource': 'ec2',
            'mode': {
                'type': 'ec2-instance-state',
                'events': ['running']},
            'filters': [
                {"tag:custodian_status": 'absent'},
                {'or': [
                    {"tag:App": 'absent'},
                    {"tag:Env": 'absent'},
                    {"tag:Owner": 'absent'}]}]},
            session_factory=session_factory)
        end = datetime.utcnow()
        start = end - timedelta(14)
        period = 24 * 60 * 60 * 14
        self.assertEqual(
            json.loads(dumps(p.get_metrics(start, end, period), indent=2)),
            {u'Durations': [],
             u'Errors': [{u'Sum': 0.0,
                          u'Timestamp': u'2016-05-30T10:50:00',
                          u'Unit': u'Count'}],
             u'Invocations': [{u'Sum': 4.0,
                               u'Timestamp': u'2016-05-30T10:50:00',
                               u'Unit': u'Count'}],
             u'ResourceCount': [{u'Average': 1.0,
                                 u'Sum': 2.0,
                                 u'Timestamp': u'2016-05-30T10:50:00',
                                 u'Unit': u'Count'}],
             u'Throttles': [{u'Sum': 0.0,
                             u'Timestamp': u'2016-05-30T10:50:00',
                             u'Unit': u'Count'}]})

    def test_policy_metrics(self):
        session_factory = self.replay_flight_data('test_policy_metrics')
        p = self.load_policy(
            {'name': 's3-encrypt-keys',
             'resource': 's3',
             'actions': [
                 {'type': 'encrypt-keys'}]},
             session_factory=session_factory)

        end = datetime.now().replace(hour=0, minute=0, microsecond=0)
        start = end - timedelta(14)
        period = 24 * 60 * 60 * 14
        self.maxDiff = None
        self.assertEqual(
            json.loads(dumps(p.get_metrics(start, end, period), indent=2)),
            {
                "ActionTime": [
                    {
                        "Timestamp": "2016-05-30T00:00:00",
                        "Average": 8541.752702140668,
                        "Sum": 128126.29053211001,
                        "Unit": "Seconds"
                    }
                ],
                "Total Keys": [
                    {
                        "Timestamp": "2016-05-30T00:00:00",
                        "Average": 1575708.7333333334,
                        "Sum": 23635631.0,
                        "Unit": "Count"
                    }
                ],
                "ResourceTime": [
                    {
                        "Timestamp": "2016-05-30T00:00:00",
                        "Average": 8.682969363532667,
                        "Sum": 130.24454045299,
                        "Unit": "Seconds"
                    }
                ],
                "ResourceCount": [
                    {
                        "Timestamp": "2016-05-30T00:00:00",
                        "Average": 23.6,
                        "Sum": 354.0,
                        "Unit": "Count"
                    }
                ],
                "Unencrypted": [
                    {
                        "Timestamp": "2016-05-30T00:00:00",
                        "Average": 10942.266666666666,
                        "Sum": 164134.0,
                        "Unit": "Count"
                    }
                ]})

    def test_get_resource_manager(self):
        collection = self.load_policy_set(
            {'policies': [
                {'name': 'query-instances',
                 'resource': 'ec2',
                 'filters': [
                     {'tag-key': 'CMDBEnvironment'}
                 ]}]})
        p = collection.policies()[0]
        self.assertTrue(
            isinstance(p.get_resource_manager(), EC2))

    def xtest_policy_run(self):
        manager.resources.register('dummy', DummyResource)
        self.addCleanup(manager.resources.unregister, 'dummy')
        self.output_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.output_dir)

        collection = self.load_policy_set(
            {'policies': [
                {'name': 'process-instances',
                 'resource': 'dummy'}]},
            {'output_dir': self.output_dir})
        p = collection.policies()[0]
        p()
        self.assertEqual(len(p.ctx.metrics.data), 3)
