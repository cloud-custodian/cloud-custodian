# Copyright 2016-2017 Capital One Services, LLC
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

import json

from botocore.exceptions import ClientError
from .common import BaseTest, functional, TestConfig as Config
from c7n.executor import MainThreadExecutor
from c7n.resources.awslambda import AWSLambda, ReservedConcurrency
from c7n.mu import PythonPackageArchive


SAMPLE_FUNC = """\
def handler(event, context):
    print("hello world")
"""


class LambdaPermissionTest(BaseTest):

    def create_function(self, client, name):
        archive = PythonPackageArchive()
        self.addCleanup(archive.remove)
        archive.add_contents('index.py', SAMPLE_FUNC)
        archive.close()

        lfunc = client.create_function(
            FunctionName=name,
            Runtime="python2.7",
            MemorySize=128,
            Handler='index.handler',
            Publish=True,
            Role='arn:aws:iam::644160558196:role/lambda_basic_execution',
            Code={'ZipFile': archive.get_bytes()})
        self.addCleanup(client.delete_function, FunctionName=name)
        return lfunc

    @functional
    def test_lambda_permission_matched(self):
        factory = self.replay_flight_data('test_lambda_permission_matched')
        client = factory().client('lambda')
        name = "func-b"

        self.create_function(client, name)
        client.add_permission(
            FunctionName=name,
            StatementId="PublicInvoke",
            Principal="*",
            Action="lambda:InvokeFunction")
        client.add_permission(
            FunctionName=name,
            StatementId="SharedInvoke",
            Principal="arn:aws:iam::185106417252:root",
            Action="lambda:InvokeFunction")
        p = self.load_policy({
            'name': 'lambda-perms',
            'resource': 'lambda',
            'filters': [
                {'FunctionName': name},
                {'type': 'cross-account',
                 'whitelist': ["185106417252"]}],
            'actions': [{
                'type': 'remove-statements',
                'statement_ids': 'matched'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        policy = json.loads(client.get_policy(FunctionName=name).get('Policy'))
        self.assertEqual(
            [s['Sid'] for s in policy.get('Statement', ())],
            ['SharedInvoke'])

    @functional
    def test_lambda_permission_named(self):
        factory = self.replay_flight_data('test_lambda_permission_named')
        client = factory().client('lambda')
        name = "func-d"

        self.create_function(client, name)
        client.add_permission(
            FunctionName=name,
            StatementId="PublicInvoke",
            Principal="*",
            Action="lambda:InvokeFunction")

        p = self.load_policy({
            'name': 'lambda-perms',
            'resource': 'lambda',
            'filters': [{'FunctionName': name}],
            'actions': [{
                'type': 'remove-statements',
                'statement_ids': ['PublicInvoke']}]},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertRaises(
            ClientError, client.get_policy, FunctionName=name)


class LambdaTest(BaseTest):

    def test_delete(self):
        factory = self.replay_flight_data('test_aws_lambda_delete')
        p = self.load_policy({
            'name': 'lambda-events',
            'resource': 'lambda',
            'filters': [
                {'FunctionName': 'superduper'}],
            'actions': [{'type': 'delete'}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['FunctionName'], 'superduper')
        client = factory().client('lambda')
        self.assertEqual(client.list_functions()['Functions'], [])

    def test_delete_reserved_concurrency(self):
        self.patch(ReservedConcurrency, 'executor_factory', MainThreadExecutor)
        factory = self.replay_flight_data('test_aws_lambda_delete_concurrency')
        p = self.load_policy({
            'name': 'lambda-concurrency',
            'resource': 'lambda',
            'filters': [
                {'FunctionName': 'envcheck'},
                {'type': 'reserved-concurrency', 'value': 'present'}],
            'actions': [
                {'type': 'set-concurrency',
                 'value': None}],
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['FunctionName'], 'envcheck')

        client = factory().client('lambda')
        info = client.get_function(FunctionName=resources[0]['FunctionName'])
        self.assertFalse('Concurrency' in info)

    def test_set_expr_concurrency(self):
        self.patch(ReservedConcurrency, 'executor_factory', MainThreadExecutor)
        factory = self.replay_flight_data('test_aws_lambda_set_concurrency_expr')
        p = self.load_policy({
            'name': 'lambda-concurrency',
            'resource': 'lambda',
            'filters': [
                {'type': 'metrics',
                 'name': 'Invocations',
                 'statistics': 'Sum',
                 'op': 'greater-than',
                 'value': 0}],
            'actions': [
                {'type': 'set-concurrency',
                 'expr': True,
                 'value':  "\"c7n.metrics\".\"AWS/Lambda.Invocations.Sum\"[0].Sum"}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['FunctionName'], 'envcheck')

        client = factory().client('lambda')
        info = client.get_function(FunctionName=resources[0]['FunctionName'])
        self.assertEqual(info['Concurrency']['ReservedConcurrentExecutions'], 5)

    def test_set_filter_concurrency(self):
        self.patch(ReservedConcurrency, 'executor_factory', MainThreadExecutor)
        factory = self.replay_flight_data('test_aws_lambda_set_concurrency')
        p = self.load_policy({
            'name': 'lambda-concurrency',
            'resource': 'lambda',
            'filters': [
                {'type': 'reserved-concurrency',
                 'value': 'absent'}],
            'actions': [
                {'type': 'set-concurrency',
                 'value': 10}]}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['FunctionName'], 'envcheck')

        client = factory().client('lambda')
        info = client.get_function(FunctionName=resources[0]['FunctionName'])
        self.assertEqual(info['Concurrency']['ReservedConcurrentExecutions'], 10)
                 
    def test_event_source(self):
        factory = self.replay_flight_data('test_aws_lambda_source')
        p = self.load_policy({
            'name': 'lambda-events',
            'resource': 'lambda',
            'filters': [
                {'type': 'event-source',
                 'key': '',
                 'value': 'not-null'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            {r['c7n:EventSources'][0] for r in resources},
            set(['iot.amazonaws.com']))

    def test_sg_filter(self):
        factory = self.replay_flight_data('test_aws_lambda_sg')

        p = self.load_policy({
            'name': 'sg-lambda',
            'resource': 'lambda',
            'filters': [
                {'FunctionName': 'mys3'},
                {'type': 'security-group',
                 'key': 'GroupName',
                 'value': 'default'}
                ]}, session_factory=factory)
        resources = p.run()
        self.assertEqual(resources[0]['FunctionName'], 'mys3')
        self.assertEqual(
            resources[0]['c7n:matched-security-groups'],
            ['sg-f9cc4d9f'])


class LambdaTagTest(BaseTest):

    def test_lambda_tag_and_remove(self):
        self.patch(AWSLambda, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_lambda_tag_and_remove')
        client = session_factory().client('lambda')

        policy = self.load_policy({
            'name': 'lambda-tag',
            'resource': 'lambda',
            'filters': [
                {'FunctionName': 'CloudCustodian'}],
            'actions': [
                {'type': 'tag', 'key': 'xyz', 'value': 'abcdef'}]
            },
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['FunctionArn']
        tags = client.list_tags(Resource=arn)['Tags']
        self.assertTrue('xyz' in tags.keys())

        policy = self.load_policy({
            'name': 'lambda-tag',
            'resource': 'lambda',
            'filters': [
                {'FunctionName': 'CloudCustodian'}],
            'actions': [
                {'type': 'remove-tag', 'tags': ['xyz']}]
            },
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['FunctionArn']
        tags = client.list_tags(Resource=arn)['Tags']
        self.assertFalse('xyz' in tags.keys())

    def test_lambda_tags(self):
        self.patch(AWSLambda, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data(
            'test_lambda_tags')
        policy = self.load_policy({
            'name': 'lambda-mark',
            'resource': 'lambda',
            'filters': [{"tag:Language": "Python"}]},
            config=Config.empty(),
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['FunctionName'], 'CloudCustodian')

    def test_mark_and_match(self):
        session_factory = self.replay_flight_data(
            'test_lambda_mark_and_match')
        client = session_factory().client('lambda')
        policy = self.load_policy({
            'name': 'lambda-mark',
            'resource': 'lambda',
            'filters': [{"FunctionName": 'CloudCustodian'}],
            'actions': [{
                'type': 'mark-for-op', 'op': 'delete',
                'tag': 'custodian_next', 'days': 1}]},
            config=Config.empty(),
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['FunctionArn']
        tags = client.list_tags(Resource=arn)['Tags']
        self.assertTrue('custodian_next' in tags.keys())

        policy = self.load_policy({
            'name': 'lambda-mark-filter',
            'resource': 'lambda',
            'filters': [
                {'type': 'marked-for-op', 'tag': 'custodian_next',
                 'op': 'delete'}]},
            config=Config.empty(),
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)
