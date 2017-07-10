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

from datetime import datetime, timedelta
import json
import shutil
import tempfile

from c7n import policy, manager
from c7n.resources.ec2 import EC2
from c7n.utils import dumps

from .common import BaseTest, Config, Bag


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


class PolicyPermissions(BaseTest):

    def test_policy_detail_spec_permissions(self):
        policy = self.load_policy({
            'name': 'kinesis-delete',
            'resource': 'kinesis',
            'actions': ['delete']})
        perms = policy.get_permissions()
        self.assertEqual(
            perms,
            set(('kinesis:DescribeStream',
                 'kinesis:ListStreams',
                 'kinesis:DeleteStream')))

    def test_policy_manager_custom_permissions(self):
        policy = self.load_policy({
            'name': 'ec2-utilization',
            'resource': 'ec2',
            'filters': [
                {'type': 'metrics',
                 'name': 'CPUUtilization',
                 'days': 3,
                 'value': 1.5}
            ]})
        perms = policy.get_permissions()
        self.assertEqual(
            perms,
            set(('ec2:DescribeInstances',
                 'ec2:DescribeTags',
                 'cloudwatch:GetMetricStatistics')))

    def test_resource_permissions(self):
        self.capture_logging('c7n.cache')
        missing = []
        cfg = Config.empty()
        for k, v in manager.resources.items():

            p = Bag({'name': 'permcheck', 'resource': k})
            ctx = self.get_context(config=cfg, policy=p)

            mgr = v(ctx, p)
            perms = mgr.get_permissions()
            if not perms:
                missing.append(k)

            for n, a in v.action_registry.items():
                p['actions'] = [n]
                perms = a({}, mgr).get_permissions()
                found = bool(perms)
                if not isinstance(perms, (list, tuple, set)):
                    found = False

                if not found:
                    missing.append("%s.actions.%s" % (
                        k, n))

            for n, f in v.filter_registry.items():
                if n in ('and', 'or', 'not'):
                    continue
                p['filters'] = [n]
                perms = f({}, mgr).get_permissions()
                if not isinstance(perms, (tuple, list, set)):
                    missing.append("%s.filters.%s" % (
                        k, n))

                # in memory filters
                if n in ('event', 'value', 'tag-count',
                         'marked-for-op', 'offhour', 'onhour', 'age',
                         'state-age', 'egress', 'ingress',
                         'capacity-delta', 'is-ssl', 'global-grants',
                         'missing-policy-statement', 'missing-statement',
                         'healthcheck-protocol-mismatch', 'image-age',
                         'has-statement',
                         'instance-age', 'ephemeral', 'instance-uptime'):
                    continue
                if not perms:
                    missing.append("%s.filters.%s" % (
                        k, n))
        if missing:
            self.fail("Missing permissions %d on \n\t%s" % (
                len(missing),
                "\n\t".join(sorted(missing))))


class TestPolicyCollection(BaseTest):

    def test_expand_partitions(self):
        cfg = Config.empty(
            regions=['us-gov-west-1', 'cn-north-1', 'us-west-2'])
        original = policy.PolicyCollection.from_data(
            {'policies': [
                {'name': 'foo',
                 'resource': 'ec2'}]},
            cfg)
        collection = original.expand_regions(cfg.regions)
        self.assertEqual(
            sorted([p.options.region for p in collection]),
            ['cn-north-1', 'us-gov-west-1', 'us-west-2'])

    def test_policy_account_expand(self):
        original = policy.PolicyCollection.from_data(
            {'policies': [
                {'name': 'foo',
                 'resource': 'account'}]},
            Config.empty(regions=['us-east-1', 'us-west-2']))

        collection = original.expand_regions(['all'])
        self.assertEqual(len(collection), 1)

    def test_policy_region_expand_global(self):
        original = policy.PolicyCollection.from_data(
            {'policies': [
                {'name': 'foo',
                 'resource': 's3'},
                {'name': 'iam',
                 'resource': 'iam-user'}]},
            Config.empty(regions=['us-east-1', 'us-west-2']))

        collection = original.expand_regions(['all'])
        self.assertEqual(len(collection.resource_types), 2)
        self.assertEqual(len(collection), 15)        
        iam = [p for p in collection if p.resource_type == 'iam-user']
        self.assertEqual(len(iam), 1)
        self.assertEqual(iam[0].options.region, 'us-east-1')

        collection = original.expand_regions(['eu-west-1', 'eu-west-2'])
        iam = [p for p in collection if p.resource_type == 'iam-user']
        self.assertEqual(len(iam), 1)
        self.assertEqual(iam[0].options.region, 'eu-west-1')
        self.assertEqual(len(collection), 3)


class TestPolicy(BaseTest):

    def test_load_policy_validation_error(self):
        invalid_policies = {
            'policies':
            [{
                'name': 'foo',
                'resource': 's3',
                'filters': [{"tag:custodian_tagging": "not-null"}],
                'actions': [{'type': 'untag',
                             'tags': {'custodian_cleanup': 'yes'}}],
            }]
        }
        self.assertRaises(Exception, self.load_policy_set, invalid_policies)


    def test_policy_validation(self):
        policy = self.load_policy({
            'name': 'ec2-utilization',
            'resource': 'ec2',
            'tags': ['abc'],
            'filters': [
                {'type': 'metrics',
                 'name': 'CPUUtilization',
                 'days': 3,
                 'value': 1.5}],
            'actions': ['stop']})
        policy.validate()
        self.assertEqual(policy.tags, ['abc'])
        self.assertFalse(policy.is_lambda)
        self.assertTrue(
            repr(policy).startswith(
                "<Policy resource: ec2 name: ec2-utilization"))

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

        self.assertIn('s3-remediate', collection)
        self.assertNotIn('s3-argle-bargle', collection)

        # Make sure __iter__ works
        for p in collection:
            self.assertTrue(p.name is not None)

        self.assertEqual(collection.resource_types, set(('s3', 'ec2')))
        self.assertTrue('s3-remediate' in collection)

        self.assertEqual(
            [p.name for p in collection.filter('s3*')],
            ['s3-remediate', 's3-global-grants'])

        self.assertEqual(
            [p.name for p in collection.filter('ec2*')],
            ['ec2-tag-compliance-stop',
             'ec2-tag-compliance-kill',
             'ec2-tag-compliance-remove'])

    def test_file_not_found(self):
        self.assertRaises(
            IOError, policy.load, Config.empty(), "/asdf12")

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
        p = collection.policies[0]
        self.assertTrue(
            isinstance(p.get_resource_manager(), EC2))

    def test_get_logs_from_group(self):
        p_data = {
            'name': 'related-rds-test',
            'resource': 'rds',
            'filters': [
                {
                    'key': 'GroupName',
                    'type': 'security-group',
                    'value': 'default',
                },
            ],
            'actions': [{'days': 10, 'type': 'retention'}],
        }
        session_factory = self.replay_flight_data('test_logs_from_group')
        config = {'log_group': 'test-logs'}
        policy = self.load_policy(p_data, config, session_factory)
        logs = list(
            policy.get_logs('2016-11-01 00:00:00', '2016-11-30 11:59:59')
        )
        self.assertEqual(len(logs), 6)
        # entries look reasonable
        entry = logs[1]
        self.assertIn('timestamp', entry)
        self.assertIn('message', entry)
        # none in range
        logs = list(
            policy.get_logs('2016-10-01 00:00:00', '2016-10-31 11:59:59')
        )
        self.assertEqual(len(logs), 0)

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
        p = collection.policies[0]
        p()
        self.assertEqual(len(p.ctx.metrics.data), 3)


class PolicyExecutionModeTest(BaseTest):

    def test_run_unimplemented(self):
        self.assertRaises(NotImplementedError,
            policy.PolicyExecutionMode({}).run)

    def test_get_logs_unimplemented(self):
        self.assertRaises(NotImplementedError,
            policy.PolicyExecutionMode({}).get_logs, 1, 2)


class PullModeTest(BaseTest):

    def test_skip_when_region_not_equal(self):
        log_file = self.capture_logging('custodian.policy')

        policy_name = 'rds-test-policy'
        p = self.load_policy(
            {'name': policy_name,
             'resource': 'rds',
             'region': 'us-east-1',
             'filters': [
                 {'type': 'default-vpc'}]},
            config={'region': 'us-west-2'},
            session_factory=None)

        p.run()

        lines = log_file.getvalue().strip().split('\n')
        self.assertIn(
            "Skipping policy {} target-region: us-east-1 current-region: us-west-2".format(policy_name),
            lines)
