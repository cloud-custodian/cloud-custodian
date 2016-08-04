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
import json
import os
import tempfile

from unittest import TestCase
from common import load_data, BaseTest

from c7n.filters.iamaccess import check_cross_account, CrossAccountAccessFilter
from c7n.mu import LambdaManager, LambdaFunction, PythonPackageArchive
from c7n.resources.sns import SNS
from c7n.executor import MainThreadExecutor


class IAMMFAFilter(BaseTest):

    def test_iam_mfa_filter(self):
        session_factory = self.replay_flight_data('test_iam_mfa_filter')
        p = self.load_policy({
            'name': 'iam-mfa',
            'resource': 'iam-user',
            'filters': [
                {'type': 'mfa-device',
                 'value': []}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)


class KMSCrossAccount(BaseTest):

    def test_kms_cross_account(self):
        self.patch(
            CrossAccountAccessFilter, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_cross_account_kms')
        client = session_factory().client('kms')

        policy = {
            'Id': 'Lulu',
            'Version': '2012-10-17',
            'Statement': [
                {"Sid": "Enable IAM User Permissions",
                 "Effect": "Allow",
                 "Principal": {"AWS": "arn:aws:iam::644160558196:root"},
                 "Action": "kms:*",
                 "Resource": "*"},
                {"Sid": "Enable Cross Account",
                 "Effect": "Allow",
                 "Principal": "*",
                 "Action": "kms:Encrypt",
                 "Resource": "*"}]
            }

        key_info = client.create_key(
            Policy=json.dumps(policy),
            Description='test-cross-account-3')['KeyMetadata']

        # disable and schedule deletion
        self.addCleanup(
            client.schedule_key_deletion,
            KeyId=key_info['KeyId'], PendingWindowInDays=7)
        self.addCleanup(client.disable_key, KeyId=key_info['KeyId'])
        
        p = self.load_policy(
            {'name': 'kms-cross',
             'resource': 'kms-key',
             'filters': [
                 {'KeyState': 'Enabled'},
                 'cross-account']},
            session_factory=session_factory)
        
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['KeyId'], key_info['KeyId'])


class GlacierCrossAccount(BaseTest):

    def test_glacier_cross_account(self):
        self.patch(
            CrossAccountAccessFilter, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_cross_account_glacier')
        client = session_factory().client('glacier')
        name = 'c7n-cross-check'
        
        url = client.create_vault(vaultName=name)['location']
        self.addCleanup(client.delete_vault, vaultName=name)

        account_id = url.split('/')[1]
        arn = "arn:aws:glacier:%s:%s:vaults/%s" % (
            os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
            account_id, name)
        
        policy = {
            'Id': 'Foo',
            "Version": "2012-10-17",
            'Statement': [
                {'Action': 'glacier:UploadArchive',
                 'Resource': arn,
                 'Effect': 'Allow',
                 'Principal': '*'}]}
        
        client.set_vault_access_policy(
            vaultName=name, policy={'Policy': json.dumps(policy)})
    
        p = self.load_policy(
            {'name': 'glacier-cross',
             'resource': 'glacier',
             'filters': ['cross-account']},
            session_factory=session_factory)
        
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['VaultName'], name)


LAMBDA_SRC = """\
def handler(event, context):
    return {'Success': True}
"""


class LambdaCrossAccount(BaseTest):

    role = "arn:aws:iam::644160558196:role/lambda_basic_execution"

    def test_lambda_cross_account(self):
        self.patch(
            CrossAccountAccessFilter, 'executor_factory', MainThreadExecutor)
        
        session_factory = self.replay_flight_data('test_cross_account_lambda')
        client = session_factory().client('lambda')
        name = 'c7n-cross-check'

        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, tmp_dir)
        archive = PythonPackageArchive(tmp_dir, tmp_dir)
        archive.create()
        archive.add_contents('handler.py', LAMBDA_SRC)
        archive.close()

        func = LambdaFunction({
            'runtime': 'python2.7',
            'name': name, 'description': '',
            'handler': 'handler.handler',
            'memory_size': 128,
            'timeout': 5,
            'role': self.role}, archive)
        manager = LambdaManager(session_factory)
        info = manager.publish(func)
        self.addCleanup(manager.remove, func)

        client.add_permission(
            FunctionName=name,
            StatementId='oops',
            Principal='*',
            Action='lambda:InvokeFunction')

        p = self.load_policy(
            {'name': 'lambda-cross',
             'resource': 'lambda',
             'filters': ['cross-account']},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['FunctionName'], name)


class ECRCrossAccount(BaseTest):

    def test_ecr_cross_account(self):
        session_factory = self.replay_flight_data('test_cross_account_ecr')
        client = session_factory().client('ecr')
        repo_name = 'c7n/cross-check'
        
        repo = client.create_repository(repositoryName=repo_name)['repository']
        self.addCleanup(client.delete_repository, repositoryName=repo_name)
        
        policy = {
            'Id': 'Foo',
            "Version": "2012-10-17",
            'Statement': [
                {'Action': 'ecr:BatchGetImage',
                 'Effect': 'Allow',
                 'Principal': '*'}]}
        
        client.set_repository_policy(
            repositoryName=repo_name, policyText=json.dumps(policy))
    
        p = self.load_policy(
            {'name': 'ecr-cross',
             'resource': 'ecr',
             'filters': ['cross-account']},
            session_factory=session_factory)
        
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['repositoryName'], repo_name)


class SQSCrossAccount(BaseTest):

    def test_sqs_cross_account(self):

        session_factory = self.replay_flight_data('test_cross_account_sqs')
        client = session_factory().client('sqs')
        queue_name = 'c7n-cross-check'
        url = client.create_queue(QueueName=queue_name)['QueueUrl']
        self.addCleanup(client.delete_queue, QueueUrl=url)
        account_id = url.split('/')[3]
        arn = "arn:aws:sqs:%s:%s:%s" % (
            os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
            account_id, queue_name)

        policy = {
            'Id': 'Foo',
            "Version": "2012-10-17",
            'Statement': [
                {'Action': 'SQS:SendMessage',
                 'Effect': 'Allow',
                 'Resource': arn,
                 'Principal': '*'}]}
        
        client.set_queue_attributes(
            QueueUrl=url, Attributes={'Policy': json.dumps(policy)})
    
        p = self.load_policy(
            {'name': 'sqs-cross',
             'resource': 'sqs',
             'filters': ['cross-account']},
            session_factory=session_factory)
        
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['QueueUrl'], url)
        

class SNSCrossAccount(BaseTest):

    def test_sns_cross_account(self):
        self.patch(SNS, 'executor_factory', MainThreadExecutor)

        session_factory = self.replay_flight_data('test_cross_account_sns')
        client = session_factory().client('sns')
        topic_name = 'c7n-cross-check'
        arn = client.create_topic(Name=topic_name)['TopicArn']
        self.addCleanup(client.delete_topic, TopicArn=arn)


        policy = {
            'Id': 'Foo',
            "Version": "2012-10-17",
            'Statement': [
                {'Action': 'SNS:Publish',
                 'Effect': 'Allow',
                 'Resource': arn,
                 'Principal': '*'}]}
        
        client.set_topic_attributes(
            TopicArn=arn, AttributeName='Policy',
            AttributeValue=json.dumps(policy))
    
        p = self.load_policy(
            {'name': 'sns-cross',
             'resource': 'sns',
             'filters': ['cross-account']},
            session_factory=session_factory)
        
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['TopicArn'], arn)
        

class CrossAccountChecker(TestCase):

    def test_not_principal_allowed(self):
        policy = {
            'Id': 'Foo',
            "Version": "2012-10-17",
            'Statement': [
                {'Action': 'SQS:ReceiveMessage',
                 'Effect': 'Deny',
                 'Principal': '*'},
                {'Action': 'SQS:SendMessage',
                 'Effect': 'Allow',
                 'NotPrincipal': '90120'}]}
        self.assertTrue(
            bool(check_cross_account(policy, set(['221800032964']))))

    def test_sqs_policies(self):
        policies = load_data('iam/sqs-policies.json')
        for p, expected in zip(
                policies, [False, True, True, False,
                           False, False, False, False]):
            violations = check_cross_account(p, set(['221800032964']))
            self.assertEqual(bool(violations), expected)
