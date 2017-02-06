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
import logging
import time
import unittest
import StringIO
import zipfile

from c7n.mu import (
    custodian_archive, LambdaManager, PolicyLambda,
    CloudWatchLogSubscription, SNSSubscription, RUNTIME)
from c7n.policy import Policy
from c7n.ufuncs import logsub
from common import BaseTest, Config, event_data
from data import helloworld


class PolicyLambdaProvision(BaseTest):

    role = "arn:aws:iam::619193117841:role/lambda_basic_execution"

    def assert_items(self, result, expected):
        for k, v in expected.items():
            self.assertEqual(v, result[k])

    def test_config_rule_provision(self):
        session_factory = self.replay_flight_data('test_config_rule')
        p = Policy({
            'resource': 'security-group',
            'name': 'sg-modified',
            'mode': {'type': 'config-rule'},
        }, Config.empty())
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        result = mgr.publish(pl, 'Dev', role=self.role)
        self.assertEqual(result['FunctionName'], 'custodian-sg-modified')
        self.addCleanup(mgr.remove, pl)

    def test_config_rule_evaluation(self):
        session_factory = self.replay_flight_data('test_config_rule_evaluate')
        p = self.load_policy({
            'resource': 'ec2',
            'name': 'ec2-modified',
            'mode': {'type': 'config-rule'},
            'filters': [{'InstanceId': 'i-094bc87c84d56c589'}]
            }, session_factory=session_factory)
        mode = p.get_execution_mode()
        event = event_data('event-config-rule-instance.json')
        resources = mode.run(event, None)
        self.assertEqual(len(resources), 1)

    def test_cwl_subscriber(self):
        self.patch(CloudWatchLogSubscription, 'iam_delay', 0.01)
        session_factory = self.replay_flight_data('test_cwl_subscriber')
        session = session_factory()
        client = session.client('logs')

        lname = "custodian-test-log-sub"
        self.addCleanup(client.delete_log_group, logGroupName=lname)
        client.create_log_group(logGroupName=lname)
        linfo = client.describe_log_groups(
            logGroupNamePrefix=lname)['logGroups'][0]

        params = dict(
            session_factory=session_factory,
            name="c7n-log-sub",
            role=self.role,
            sns_topic="arn:",
            log_groups=[linfo])

        func = logsub.get_function(**params)
        manager = LambdaManager(session_factory)
        finfo = manager.publish(func)
        self.addCleanup(manager.remove, func)

        results = client.describe_subscription_filters(logGroupName=lname)
        self.assertEqual(len(results['subscriptionFilters']), 1)
        self.assertEqual(results['subscriptionFilters'][0]['destinationArn'],
                         finfo['FunctionArn'])
        # try and update
        #params['sns_topic'] = "arn:123"
        #manager.publish(func)

    def test_sns_subscriber(self):
        self.patch(SNSSubscription, 'iam_delay', 0.01)
        session_factory = self.replay_flight_data('test_sns_subscriber')
        session = session_factory()
        client = session.client('sns')

        # create an sns topic
        tname = "custodian-test-sns-sub"
        topic_arn = client.create_topic(Name=tname)['TopicArn']
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        # provision a lambda via mu
        params = dict(
            session_factory=session_factory,
            name='c7n-hello-world',
            role='arn:aws:iam::644160558196:role/custodian-mu',
            events=[SNSSubscription(session_factory, [topic_arn])])

        func = helloworld.get_function(**params)
        manager = LambdaManager(session_factory)
        manager.publish(func)
        self.addCleanup(manager.remove, func)

        # now publish to the topic and look for lambda log output
        client.publish(TopicArn=topic_arn, Message='Greetings, program!')
        #time.sleep(15) -- turn this back on when recording flight data
        log_events = manager.logs(func, '1970-1-1', '9170-1-1')
        messages = [e['message'] for e in log_events
                    if e['message'].startswith('{"Records')]
        self.addCleanup(
            session.client('logs').delete_log_group,
            logGroupName='/aws/lambda/c7n-hello-world')
        self.assertEqual(
            json.loads(messages[0])['Records'][0]['Sns']['Message'],
            'Greetings, program!')

    def test_cwe_update_config_and_code(self):
        # Originally this was testing the no update case.. but
        # That is tricky to record, any updates to the code end up
        # causing issues due to checksum mismatches which imply updating
        # the function code / which invalidate the recorded data and
        # the focus of the test.

        session_factory = self.replay_flight_data(
            'test_cwe_update', zdata=True)
        p = Policy({
            'resource': 's3',
            'name': 's3-bucket-policy',
            'mode': {
                'type': 'cloudtrail',
                'events': ["CreateBucket"],
            },
            'filters': [
                {'type': 'missing-policy-statement',
                 'statement_ids': ['RequireEncryptedPutObject']}],
            'actions': ['no-op']
        }, Config.empty())
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        result = mgr.publish(pl, 'Dev', role=self.role)
        self.addCleanup(mgr.remove, pl)

        p = Policy({
            'resource': 's3',
            'name': 's3-bucket-policy',
            'mode': {
                'type': 'cloudtrail',
                'memory': 256,
                'events': [
                    "CreateBucket",
                    {'event': 'PutBucketPolicy',
                     'ids': 'requestParameters.bucketName',
                     'source': 's3.amazonaws.com'}]
            },
            'filters': [
                {'type': 'missing-policy-statement',
                 'statement_ids': ['RequireEncryptedPutObject']}],
            'actions': ['no-op']
        }, Config.empty())

        output = self.capture_logging('custodian.lambda', level=logging.DEBUG)
        result2 = mgr.publish(PolicyLambda(p), 'Dev', role=self.role)

        lines = output.getvalue().strip().split('\n')
        self.assertTrue(
            'Updating function custodian-s3-bucket-policy code' in lines)
        self.assertTrue(
            'Updating function: custodian-s3-bucket-policy config' in lines)
        self.assertEqual(result['FunctionName'], result2['FunctionName'])
        # drive by coverage
        functions = [i for i in mgr.list_functions()
                     if i['FunctionName'] == 'custodian-s3-bucket-policy']
        self.assertTrue(len(functions), 1)
        start = 0L
        end = long(time.time() * 1000)
        self.assertEqual(list(mgr.logs(pl, start, end)), [])

    def test_cwe_trail(self):
        session_factory = self.replay_flight_data('test_cwe_trail', zdata=True)
        p = Policy({
            'resource': 's3',
            'name': 's3-bucket-policy',
            'mode': {
                'type': 'cloudtrail',
                'events': ["CreateBucket"],
            },
            'filters': [
                {'type': 'missing-policy-statement',
                 'statement_ids': ['RequireEncryptedPutObject']}],
            'actions': ['no-op']
        }, Config.empty())
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        result = mgr.publish(pl, 'Dev', role=self.role)

        events = pl.get_events(session_factory)
        self.assertEqual(len(events), 1)
        event = events.pop()
        self.assertEqual(
            json.loads(event.render_event_pattern()),
            {u'detail': {u'eventName': [u'CreateBucket'],
                         u'eventSource': [u's3.amazonaws.com']},
             u'detail-type': ['AWS API Call via CloudTrail']})

        self.assert_items(
            result,
            {'Description': 'cloud-custodian lambda policy',
             'FunctionName': 'custodian-s3-bucket-policy',
             'Handler': 'custodian_policy.run',
             'MemorySize': 512,
             'Runtime': RUNTIME,
             'Timeout': 60})
        mgr.remove(pl)

    def test_mu_metrics(self):
        session_factory = self.replay_flight_data('test_mu_metrics')
        p = Policy({
            'resources': 's3',
            'name': 's3-bucket-policy',
            'resource': 's3',
            'mode': {
                'type': 'cloudtrail',
                'events': ['CreateBucket'],
                },
            'actions': ['no-op']}, Config.empty())
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        end = datetime.utcnow()
        start = end - timedelta(1)
        results = mgr.metrics([pl], start, end, 3600)
        self.assertEqual(
            results, [{'Durations': [], 'Errors': [],
                       'Throttles': [], 'Invocations': []}])

    def test_cwe_instance(self):
        session_factory = self.replay_flight_data(
            'test_cwe_instance', zdata=True)
        p = Policy({
            'resource': 's3',
            'name': 'ec2-encrypted-vol',
            'mode': {
                'type': 'ec2-instance-state',
                'events': ['pending']}
        }, Config.empty())
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        result = mgr.publish(pl, 'Dev', role=self.role)
        self.assert_items(
            result,
            {'Description': 'cloud-custodian lambda policy',
             'FunctionName': 'c7n-ec2-encrypted-vol',
             'Handler': 'c7n_policy.run',
             'MemorySize': 512,
             'Runtime': RUNTIME,
             'Timeout': 60})

        events = session_factory().client('events')
        result = events.list_rules(NamePrefix="c7n-ec2-encrypted-vol")
        self.assert_items(
            result['Rules'][0],
            {"State": "ENABLED",
             "Name": "c7n-ec2-encrypted-vol"})

        self.assertEqual(
            json.loads(result['Rules'][0]['EventPattern']),
            {"source": ["aws.ec2"],
             "detail": {
                 "state": ["pending"]},
             "detail-type": ["EC2 Instance State-change Notification"]})
        mgr.remove(pl)

    def test_cwe_asg_instance(self):
        session_factory = self.replay_flight_data('test_cwe_asg', zdata=True)
        p = Policy({
            'resource': 'asg',
            'name': 'asg-spin-detector',
            'mode': {
                'type': 'asg-instance-state',
                'events': ['launch-failure']}
        }, Config.empty())
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        result = mgr.publish(pl, 'Dev', role=self.role)
        self.assert_items(
            result,
            {'FunctionName': 'c7n-asg-spin-detector',
             'Handler': 'c7n_policy.run',
             'MemorySize': 512,
             'Runtime': RUNTIME,
             'Timeout': 60})

        events = session_factory().client('events')
        result = events.list_rules(NamePrefix="c7n-asg-spin-detector")
        self.assert_items(
            result['Rules'][0],
            {"State": "ENABLED",
             "Name": "c7n-asg-spin-detector"})

        self.assertEqual(
            json.loads(result['Rules'][0]['EventPattern']),
            {"source": ["aws.autoscaling"],
             "detail-type": ["EC2 Instance Launch Unsuccessful"]})
        mgr.remove(pl)

    def test_cwe_schedule(self):
        session_factory = self.replay_flight_data(
            'test_cwe_schedule', zdata=True)
        p = Policy({
            'resource': 'ec2',
            'name': 'periodic-ec2-checker',
            'mode': {
                'type': 'periodic',
                'schedule': 'rate(1 day)'
                }
        }, Config.empty())

        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        result = mgr.publish(pl, 'Dev', role=self.role)
        self.assert_items(
            result,
            {'FunctionName': 'c7n-periodic-ec2-checker',
             'Handler': 'c7n_policy.run',
             'MemorySize': 512,
             'Runtime': RUNTIME,
             'Timeout': 60})

        events = session_factory().client('events')
        result = events.list_rules(NamePrefix="c7n-periodic-ec2-checker")
        self.assert_items(
            result['Rules'][0],
            {
                "State": "ENABLED",
                "ScheduleExpression": "rate(1 day)",
                "Name": "c7n-periodic-ec2-checker"})
        mgr.remove(pl)


class PythonArchiveTest(unittest.TestCase):

    def test_archive_bytes(self):
        self.archive = custodian_archive()
        self.archive.create()
        self.addCleanup(self.archive.remove)
        self.archive.close()
        io = StringIO.StringIO(self.archive.get_bytes())
        reader = zipfile.ZipFile(io, mode='r')
        fileset = [n.filename for n in reader.filelist]
        self.assertTrue('c7n/__init__.py' in fileset)

    def test_archive_skip(self):
        self.archive = custodian_archive("*.pyc")
        self.archive.create()
        self.addCleanup(self.archive.remove)
        self.archive.close()
        with open(self.archive.path) as fh:
            reader = zipfile.ZipFile(fh, mode='r')
            fileset = [n.filename for n in reader.filelist]
            for i in ['c7n/__init__.pyc',
                      'c7n/resources/s3.pyc',
                      'boto3/__init__.py']:
                self.assertFalse(i in fileset)

    def test_archive_permissions(self):
        # files should all be readable
        self.archive = custodian_archive("*.pyc")
        self.archive.create()
        self.addCleanup(self.archive.remove)
        self.archive.close()
        readable = 0444 << 16L
        with open(self.archive.path) as fh:
            reader = zipfile.ZipFile(fh, mode='r')
            for i in reader.infolist():
                self.assertGreaterEqual(i.external_attr, readable)
