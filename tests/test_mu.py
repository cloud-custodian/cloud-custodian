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
import imp
import json
import logging
import os
import platform
import py_compile
import shutil
import sys
import tempfile
import time
import unittest
import zipfile

from c7n.mu import (
    custodian_archive, LambdaManager, PolicyLambda, PythonPackageArchive,
    CloudWatchLogSubscription, SNSSubscription, RUNTIME)
from c7n.policy import Policy
from c7n.ufuncs import logsub
from .common import BaseTest, Config, event_data
from .data import helloworld


class PolicyLambdaProvision(BaseTest):

    role = "arn:aws:iam::644160558196:role/custodian-mu"

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
        self.addCleanup(mgr.remove, pl)
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
        self.addCleanup(mgr.remove, pl)
        result = mgr.publish(pl, 'Dev', role=self.role)
        self.assert_items(
            result,
            {'Description': 'cloud-custodian lambda policy',
             'FunctionName': 'custodian-ec2-encrypted-vol',
             'Handler': 'custodian_policy.run',
             'MemorySize': 512,
             'Runtime': RUNTIME,
             'Timeout': 60})

        events = session_factory().client('events')
        result = events.list_rules(NamePrefix="custodian-ec2-encrypted-vol")
        self.assert_items(
            result['Rules'][0],
            {"State": "ENABLED",
             "Name": "custodian-ec2-encrypted-vol"})

        self.assertEqual(
            json.loads(result['Rules'][0]['EventPattern']),
            {"source": ["aws.ec2"],
             "detail": {
                 "state": ["pending"]},
             "detail-type": ["EC2 Instance State-change Notification"]})

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
        self.addCleanup(mgr.remove, pl)
        result = mgr.publish(pl, 'Dev', role=self.role)
        self.assert_items(
            result,
            {'FunctionName': 'custodian-asg-spin-detector',
             'Handler': 'custodian_policy.run',
             'MemorySize': 512,
             'Runtime': RUNTIME,
             'Timeout': 60})

        events = session_factory().client('events')
        result = events.list_rules(NamePrefix="custodian-asg-spin-detector")
        self.assert_items(
            result['Rules'][0],
            {"State": "ENABLED",
             "Name": "custodian-asg-spin-detector"})

        self.assertEqual(
            json.loads(result['Rules'][0]['EventPattern']),
            {"source": ["aws.autoscaling"],
             "detail-type": ["EC2 Instance Launch Unsuccessful"]})

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
        self.addCleanup(mgr.remove, pl)
        result = mgr.publish(pl, 'Dev', role=self.role)
        self.assert_items(
            result,
            {'FunctionName': 'custodian-periodic-ec2-checker',
             'Handler': 'custodian_policy.run',
             'MemorySize': 512,
             'Runtime': RUNTIME,
             'Timeout': 60})

        events = session_factory().client('events')
        result = events.list_rules(NamePrefix="custodian-periodic-ec2-checker")
        self.assert_items(
            result['Rules'][0],
            {
                "State": "ENABLED",
                "ScheduleExpression": "rate(1 day)",
                "Name": "custodian-periodic-ec2-checker"})

    key_arn = 'arn:aws:kms:us-west-2:644160558196:key/'\
        '44d25a5c-7efa-44ed-8436-b9511ea921b3'
    sns_arn = 'arn:aws:sns:us-west-2:644160558196:config-topic'

    def create_a_lambda(self, flight, **extra):
        session_factory = self.replay_flight_data(flight, zdata=True)
        mode = {
            'type': 'config-rule',
            'role':'arn:aws:iam::644160558196:role/custodian-mu'}
        mode.update(extra)
        p = Policy({
            'resource': 's3',
            'name': 'hello-world',
            'actions': ['no-op'],
            'mode': mode,
        }, Config.empty())
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        self.addCleanup(mgr.remove, pl)
        return mgr, mgr.publish(pl)

    def create_a_lambda_with_lots_of_config(self, flight):
        extra = {
            'environment': {'Variables': {'FOO': 'bar'}},
            'kms_key_arn': self.key_arn,
            'dead_letter_config': {'TargetArn': self.sns_arn},
            'tracing_config': {'Mode': 'Active'},
            'tags': {'Foo': 'Bar'}}
        return self.create_a_lambda(flight, **extra)

    def update_a_lambda(self, mgr, **config):
        mode = {
            'type': 'config-rule',
            'role':'arn:aws:iam::644160558196:role/custodian-mu'}
        mode.update(config)
        p = Policy({
            'resource': 's3',
            'name': 'hello-world',
            'actions': ['no-op'],
            'mode': mode
        }, Config.empty())
        pl = PolicyLambda(p)
        return mgr.publish(pl)

    def test_config_coverage_for_lambda_creation(self):
        mgr, result = self.create_a_lambda_with_lots_of_config(
            'test_config_coverage_for_lambda_creation')
        self.assert_items(
            result,
            {'Description': 'cloud-custodian lambda policy',
             'FunctionName': 'custodian-hello-world',
             'Handler': 'custodian_policy.run',
             'MemorySize': 512,
             'Runtime': RUNTIME,
             'Timeout': 60,
             'DeadLetterConfig': {'TargetArn': self.sns_arn},
             'Environment': {'Variables': {'FOO': 'bar'}},
             'KMSKeyArn': self.key_arn,
             'TracingConfig': {'Mode': 'Active'}})
        tags = mgr.client.list_tags(Resource=result['FunctionArn'])['Tags']
        self.assert_items(tags, {'Foo': 'Bar'})

    def test_config_coverage_for_lambda_update_from_plain(self):
        mgr, result = self.create_a_lambda(
            'test_config_coverage_for_lambda_update_from_plain')
        result = self.update_a_lambda(mgr, **{
            'environment': {'Variables': {'FOO': 'bloo'}},
            'kms_key_arn': self.key_arn,
            'dead_letter_config': {'TargetArn': self.sns_arn},
            'tracing_config': {'Mode': 'Active'},
            'tags': {'Foo': 'Bloo'}})

        self.assert_items(
            result,
            {'Description': 'cloud-custodian lambda policy',
             'FunctionName': 'custodian-hello-world',
             'Handler': 'custodian_policy.run',
             'MemorySize': 512,
             'Runtime': RUNTIME,
             'Timeout': 60,
             'DeadLetterConfig': {'TargetArn': self.sns_arn},
             'Environment': {'Variables': {'FOO': 'bloo'}},
             'TracingConfig': {'Mode': 'Active'}})
        tags = mgr.client.list_tags(Resource=result['FunctionArn'])['Tags']
        self.assert_items(tags, {'Foo': 'Bloo'})

    def test_config_coverage_for_lambda_update_from_complex(self):
        mgr, result = self.create_a_lambda_with_lots_of_config(
            'test_config_coverage_for_lambda_update_from_complex')
        result = self.update_a_lambda(mgr, **{
            'environment': {'Variables': {'FOO': 'baz'}},
            'kms_key_arn': '',
            'dead_letter_config': {},
            'tracing_config': {},
            'tags': {'Foo': 'Baz', 'Bah': 'Bug'}})

        self.assert_items(
            result,
            {'Description': 'cloud-custodian lambda policy',
             'FunctionName': 'custodian-hello-world',
             'Handler': 'custodian_policy.run',
             'MemorySize': 512,
             'Runtime': RUNTIME,
             'Timeout': 60,
             'DeadLetterConfig': {'TargetArn': self.sns_arn},
             'Environment': {'Variables': {'FOO': 'baz'}},
             'TracingConfig': {'Mode': 'Active'}})
        tags = mgr.client.list_tags(Resource=result['FunctionArn'])['Tags']
        self.assert_items(tags, {'Foo': 'Baz', 'Bah': 'Bug'})


class PythonArchiveTest(unittest.TestCase):

    def make_archive(self, *a, **kw):
        archive = self.make_open_archive(*a, **kw)
        archive.close()
        return archive

    def make_open_archive(self, *a, **kw):
        archive = PythonPackageArchive(*a, **kw)
        self.addCleanup(archive.remove)
        return archive

    def get_filenames(self, *a, **kw):
        return self.make_archive(*a, **kw).get_filenames()


    def test_handles_stdlib_modules(self):
        filenames = self.get_filenames('webbrowser')
        self.assertTrue('webbrowser.py' in filenames)

    def test_handles_third_party_modules(self):
        filenames = self.get_filenames('ipaddress')
        self.assertTrue('ipaddress.py' in filenames)

    def test_handles_packages(self):
        filenames = self.get_filenames('c7n')
        self.assertTrue('c7n/__init__.py' in filenames)
        self.assertTrue('c7n/resources/s3.py' in filenames)
        self.assertTrue('c7n/ufuncs/s3crypt.py' in filenames)

    def test_excludes_non_py_files(self):
        filenames = self.get_filenames('ctypes')
        self.assertTrue('ctypes/__init__.py' in filenames)
        self.assertTrue('ctypes/macholib/__init__.py' in filenames)
        self.assertTrue('README.ctypes' not in filenames)

    def test_cant_get_bytes_when_open(self):
        archive = self.make_open_archive()
        self.assertRaises(AssertionError, archive.get_bytes)

    def test_cant_add_files_when_closed(self):
        archive = self.make_archive()
        self.assertRaises(AssertionError, archive.add_file, __file__)

    def test_cant_add_contents_when_closed(self):
        archive = self.make_archive()
        self.assertRaises(AssertionError, archive.add_contents, 'foo', 'bar')

    def test_can_add_additional_files_while_open(self):
        archive = self.make_open_archive()
        archive.add_file(__file__)
        archive.close()
        filenames = archive.get_filenames()
        self.assertTrue(os.path.basename(__file__) in filenames)

    def test_can_set_path_when_adding_files(self):
        archive = self.make_open_archive()
        archive.add_file(__file__, 'cheese/is/yummy.txt')
        archive.close()
        filenames = archive.get_filenames()
        self.assertTrue(os.path.basename(__file__) not in filenames)
        self.assertTrue('cheese/is/yummy.txt' in filenames)

    def test_can_add_a_file_with_contents_from_a_string(self):
        archive = self.make_open_archive()
        archive.add_contents('cheese.txt', 'So yummy!')
        archive.close()
        self.assertTrue('cheese.txt' in archive.get_filenames())
        with archive.get_reader() as reader:
            self.assertEqual('So yummy!', reader.read('cheese.txt'))

    def test_custodian_archive_creates_a_custodian_archive(self):
        archive = custodian_archive()
        self.addCleanup(archive.remove)
        archive.close()
        filenames = archive.get_filenames()
        self.assertTrue('c7n/__init__.py' in filenames)
        self.assertTrue('pkg_resources/__init__.py' in filenames)
        self.assertTrue('ipaddress.py' in filenames)


    def make_file(self):
        bench = tempfile.mkdtemp()
        path = os.path.join(bench, 'foo.txt')
        open(path, 'w+').write('Foo.')
        self.addCleanup(lambda: shutil.rmtree(bench))
        return path

    def check_readable(self, archive):
        readable = 0o444 << 16L
        with open(archive.path) as fh:
            reader = zipfile.ZipFile(fh, mode='r')
            for i in reader.infolist():
                self.assertGreaterEqual(i.external_attr, readable)

    def test_files_are_all_readable(self):
        self.check_readable(self.make_archive('c7n'))

    def test_even_unreadable_files_become_readable(self):
        path = self.make_file()
        os.chmod(path, 0o600)
        archive = self.make_open_archive()
        archive.add_file(path)
        archive.close()
        self.check_readable(archive)

    def test_unless_you_make_your_own_zipinfo(self):
        info = zipfile.ZipInfo(self.make_file())
        archive = self.make_open_archive()
        archive.add_contents(info, 'foo.txt')
        archive.close()
        self.assertRaises(AssertionError, self.check_readable, archive)


class PycCase(unittest.TestCase):

    def setUp(self):
        self.bench = tempfile.mkdtemp()
        sys.path.insert(0, self.bench)

    def tearDown(self):
        sys.path.remove(self.bench)
        shutil.rmtree(self.bench)

    def py_with_pyc(self, name):
        path = os.path.join(self.bench, name)
        with open(path, 'w+') as fp:
            fp.write('42')
        py_compile.compile(path)
        return path


class Constructor(PycCase):

    def test_class_constructor_only_accepts_py_modules_not_pyc(self):

        # Create a module with both *.py and *.pyc.
        self.py_with_pyc('foo.py')

        # Create another with a *.pyc but no *.py behind it.
        os.unlink(self.py_with_pyc('bar.py'))

        # Now: *.py takes precedence over *.pyc ...
        get = lambda name: os.path.basename(imp.find_module(name)[1])
        self.assertTrue(get('foo'), 'foo.py')
        try:
            # ... and while *.pyc is importable ...
            self.assertTrue(get('bar'), 'bar.pyc')
        except ImportError:
            # (except on PyPy)
            # http://doc.pypy.org/en/latest/config/objspace.lonepycfiles.html
            self.assertEqual(platform.python_implementation(), 'PyPy')
        else:
            # ... we refuse it.
            with self.assertRaises(ValueError) as raised:
                PythonPackageArchive('bar')
            msg = raised.exception.args[0]
            self.assertTrue(msg.startswith('We need a *.py source file instead'))
            self.assertTrue(msg.endswith('bar.pyc'))

        # We readily ignore a *.pyc if a *.py exists.
        archive = PythonPackageArchive('foo')
        archive.close()
        self.assertEqual(archive.get_filenames(), ['foo.py'])
        with archive.get_reader() as reader:
            self.assertEqual('42', reader.read('foo.py'))


class AddPyFile(PycCase):

    def test_can_add_py_file(self):
        archive = PythonPackageArchive()
        archive.add_py_file(self.py_with_pyc('foo.py'))
        archive.close()
        self.assertEqual(archive.get_filenames(), ['foo.py'])

    def test_reverts_to_py_if_available(self):
        archive = PythonPackageArchive()
        py = self.py_with_pyc('foo.py')
        archive.add_py_file(py+'c')
        archive.close()
        self.assertEqual(archive.get_filenames(), ['foo.py'])

    def test_fails_if_py_not_available(self):
        archive = PythonPackageArchive()
        py = self.py_with_pyc('foo.py')
        os.unlink(py)
        self.assertRaises(IOError, archive.add_py_file, py+'c')


class DiffTags(unittest.TestCase):

    def test_empty(self):
        assert LambdaManager.diff_tags({}, {}) == ({}, [])

    def test_removal(self):
        assert LambdaManager.diff_tags({'Foo': 'Bar'}, {}) == ({}, ['Foo'])

    def test_addition(self):
        assert LambdaManager.diff_tags(
            {}, {'Foo': 'Bar'}) == ({'Foo': 'Bar'}, [])

    def test_update(self):
        assert LambdaManager.diff_tags(
            {'Foo': 'Bar'}, {'Foo': 'Baz'}) == ({'Foo': 'Baz'}, [])
