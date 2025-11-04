# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import importlib
import json
import logging
import os
import platform
import py_compile
import shutil
import site
import sys
import tempfile
import time
import unittest
from unittest import mock
from unittest.mock import patch
import zipfile


from c7n.config import Config
from c7n.mu import (
    custodian_archive,
    generate_requirements,
    get_exec_options,
    BucketLambdaNotification,
    LambdaFunction,
    LambdaManager,
    PolicyLambda,
    PythonPackageArchive,
    SNSSubscription,
    SQSSubscription,
    CloudWatchEventSource,
    CloudWatchLogSubscription
)

from .common import (
    BaseTest, event_data, functional, Bag, ACCOUNT_ID)
from .data import helloworld


ROLE = "arn:aws:iam::644160558196:role/custodian-mu"


def test_get_exec_options():

    assert get_exec_options(Config().empty()) == {'tracer': 'default'}
    assert get_exec_options(Config().empty(output_dir='/tmp/xyz')) == {
        'tracer': 'default'}
    assert get_exec_options(
        Config().empty(log_group='gcp', output_dir='gs://mybucket/myprefix')) == {
            'tracer': 'default',
            'output_dir': 'gs://mybucket/myprefix',
            'log_group': 'gcp'}


def test_generate_requirements():
    lines = generate_requirements(
        'boto3', ignore=('docutils', 's3transfer', 'six'), exclude=['urllib3'])
    packages = []
    for l in lines.split('\n'):
        pkg_name, _ = l.split('==')
        packages.append(pkg_name)
    assert set(packages) == {'botocore', 'jmespath', 'python-dateutil'}


class Publish(BaseTest):

    def make_func(self, **kw):
        func_data = dict(
            name="test-foo-bar",
            handler="index.handler",
            memory_size=128,
            timeout=3,
            role=ROLE,
            runtime="python3.12",
            description="test",
        )
        func_data.update(kw)

        archive = PythonPackageArchive()
        archive.add_contents(
            "index.py", """def handler(*a, **kw):\n    print("Greetings, program!")"""
        )
        archive.close()
        self.addCleanup(archive.remove)
        return LambdaFunction(func_data, archive)


class PolicyLambdaProvision(Publish):

    role = "arn:aws:iam::644160558196:role/custodian-mu"

    def assert_items(self, result, expected):
        for k, v in expected.items():
            self.assertEqual(v, result[k])

    def test_config_rule_provision(self):
        session_factory = self.replay_flight_data("test_config_rule")
        p = self.load_policy(
            {
                "resource": "security-group",
                "name": "sg-modified",
                "mode": {"type": "config-rule"},
            },
            session_factory=session_factory
        )
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        result = mgr.publish(pl, "Dev", role=ROLE)
        self.assertEqual(result["FunctionName"], "custodian-sg-modified")
        self.addCleanup(mgr.remove, pl)

    def test_published_lambda_architecture(self):
        session_factory = self.replay_flight_data("test_published_lambda_architecture")
        with patch('platform.machine', return_value="arm64"):
            p = self.load_policy({
                'name': 'ec2-foo-bar',
                'resource': 'aws.ec2',
                'mode': {
                    'type': 'cloudtrail',
                    'role': 'arn:aws:iam::644160558196:role/custodian-mu',
                    'events': ['RunInstances']}})
            pl = PolicyLambda(p)
            mgr = LambdaManager(session_factory)
            result = mgr.publish(pl)
            self.assertEqual(result["Architectures"], ["arm64"])

    def test_deferred_interpolation(self):
        p = self.load_policy({
            'name': 'ec2-foo-bar',
            'resource': 'aws.ec2',
            'mode': {
                'type': 'cloudtrail',
                'role': 'arn:aws:iam::644160558196:role/custodian-mu',
                'events': ['RunInstances']},
            'actions': [{
                'type': 'tag', 'key': 'LastMatch', 'value': '{now}'
            }]})
        p.expand_variables(p.get_variables())
        pl = PolicyLambda(p)
        pl.get_archive()

    def test_updated_lambda_architecture(self):
        session_factory = self.replay_flight_data("test_updated_lambda_architecture")
        lambda_client = session_factory().client("lambda")
        initial_config = lambda_client.get_function(FunctionName="custodian-ec2-foo-bar")
        self.assertEqual(initial_config.get('Configuration').get('Architectures'), ["arm64"])
        with patch('platform.machine', return_value="x86_64"):
            p1 = self.load_policy({
                'name': 'ec2-foo-bar',
                'resource': 'aws.ec2',
                'mode': {
                    'type': 'cloudtrail',
                    'role': 'arn:aws:iam::644160558196:role/custodian-mu',
                    'runtime': 'python3.12',
                    'events': ['RunInstances']}})
            pl1 = PolicyLambda(p1)
            mgr = LambdaManager(session_factory)
            mgr.publish(pl1)
            if self.recording:
                time.sleep(30)
            updated_config = lambda_client.get_function_configuration(
                FunctionName="custodian-ec2-foo-bar")
            self.assertEqual(updated_config.get('Architectures'), ["x86_64"])
            self.addCleanup(mgr.remove, pl1)

    def test_config_poll_rule_evaluation(self):
        session_factory = self.replay_flight_data("test_config_poll_rule_evaluation")

        # config added support for kinesis streams after that test was written
        # disable that support so the original behavior check on config poll mode
        # can be verified
        from c7n.resources.kinesis import KinesisStream
        self.patch(
            KinesisStream.resource_type, 'config_type', None)

        p = self.load_policy({
            'name': 'configx',
            'resource': 'aws.kinesis',
            'mode': {
                'schedule': 'Three_Hours',
                'type': 'config-poll-rule'}})
        mu_policy = PolicyLambda(p)
        mu_policy.arn = "arn:aws:lambda:us-east-1:644160558196:function:CloudCustodian"
        events = mu_policy.get_events(session_factory)
        self.assertEqual(len(events), 1)
        config_rule = events.pop()
        self.assertEqual(
            config_rule.get_rule_params(mu_policy),

            {'ConfigRuleName': 'custodian-configx',
             'Description': 'cloud-custodian lambda policy',
             'MaximumExecutionFrequency': 'Three_Hours',
             'Source': {
                 'Owner': 'CUSTOM_LAMBDA',
                 'SourceDetails': [{'EventSource': 'aws.config',
                                    'MessageType': 'ScheduledNotification'}],
                 'SourceIdentifier': 'arn:aws:lambda:us-east-1:644160558196:function:CloudCustodian'} # noqa
             })

    def test_config_rule_evaluation(self):
        session_factory = self.replay_flight_data("test_config_rule_evaluate")
        p = self.load_policy(
            {
                "resource": "ec2",
                "name": "ec2-modified",
                "mode": {"type": "config-rule"},
                "filters": [{"InstanceId": "i-094bc87c84d56c589"}],
            },
            session_factory=session_factory,
        )
        mode = p.get_execution_mode()
        event = event_data("event-config-rule-instance.json")
        resources = mode.run(event, None)
        self.assertEqual(len(resources), 1)

    def test_phd_account_mode(self):
        factory = self.replay_flight_data('test_phd_event_mode')
        p = self.load_policy(
            {'name': 'ec2-retire',
             'resource': 'account',
             'mode': {
                 'categories': ['scheduledChange'],
                 'events': ['AWS_EC2_PERSISTENT_INSTANCE_RETIREMENT_SCHEDULED'],
                 'type': 'phd'}}, session_factory=factory)
        mode = p.get_execution_mode()
        event = event_data('event-phd-ec2-retire.json')
        resources = mode.run(event, None)
        self.assertEqual(len(resources), 1)
        self.assertTrue('c7n:HealthEvent' in resources[0])

    def test_phd_mode_sans_details(self):
        factory = self.replay_flight_data('test_phd_event_mode')
        p = self.load_policy(
            {'name': 'ec2-retire',
             'resource': 'account',
             'mode': {'type': 'phd'}}, session_factory=factory)
        p_lambda = PolicyLambda(p)
        events = p_lambda.get_events(factory)
        self.assertEqual(
            json.loads(events[0].render_event_pattern()),
            {'source': ['aws.health']}
        )

    def test_phd_mode(self):
        factory = self.replay_flight_data('test_phd_event_mode')
        p = self.load_policy(
            {'name': 'ec2-retire',
             'resource': 'ec2',
             'mode': {
                 'categories': ['scheduledChange'],
                 'events': ['AWS_EC2_PERSISTENT_INSTANCE_RETIREMENT_SCHEDULED'],
                 'type': 'phd'}}, session_factory=factory)
        mode = p.get_execution_mode()
        event = event_data('event-phd-ec2-retire.json')
        resources = mode.run(event, None)
        self.assertEqual(len(resources), 1)

        p_lambda = PolicyLambda(p)
        events = p_lambda.get_events(factory)
        self.assertEqual(
            json.loads(events[0].render_event_pattern()),
            {'detail': {
                'eventTypeCategory': ['scheduledChange'],
                'eventTypeCode': ['AWS_EC2_PERSISTENT_INSTANCE_RETIREMENT_SCHEDULED']},
             'source': ['aws.health']}
        )

    def test_phd_mode_account(self):
        factory = self.replay_flight_data('test_phd_event_account')
        p = self.load_policy(
            {'name': 'ec2-retire',
             'resource': 'account',
             'mode': {
                 'categories': ['issue', 'scheduledChange'],
                 'statuses': ['open', 'upcoming'],
                 'type': 'phd'}}, session_factory=factory)

        p_lambda = PolicyLambda(p)
        events = p_lambda.get_events(factory)
        self.assertEqual(
            json.loads(events[0].render_event_pattern()),
            {'detail': {
                'eventTypeCategory': ['issue', 'scheduledChange']},
             'source': ['aws.health']}
        )

    def test_cloudtrail_delay(self):
        p = self.load_policy({
            'name': 'aws-account',
            'resource': 'aws.account',
            'mode': {
                'type': 'cloudtrail',
                'delay': 32,
                'role': 'CustodianRole',
                'events': ['RunInstances']}})
        from c7n import policy

        class time:

            invokes = []

            @classmethod
            def sleep(cls, duration):
                cls.invokes.append(duration)

        self.patch(policy, 'time', time)
        trail_mode = p.get_execution_mode()
        results = trail_mode.run({
            'detail': {
                'eventSource': 'ec2.amazonaws.com',
                'eventName': 'RunInstances'}},
            None)
        self.assertEqual(len(results), 0)
        self.assertEqual(time.invokes, [32])

    def test_user_pattern_merge(self):
        p = self.load_policy({
            'name': 'ec2-retire',
            'resource': 'ec2',
            'mode': {
                'type': 'cloudtrail',
                'pattern': {
                    'detail': {
                        'userIdentity': {
                            'userName': [{'anything-but': 'deputy'}]}}},
                'events': [{
                    'ids': 'responseElements.subnet.subnetId',
                    'source': 'ec2.amazonaws.com',
                    'event': 'CreateSubnet'}]}})
        p_lambda = PolicyLambda(p)
        events = p_lambda.get_events(None)
        self.assertEqual(
            json.loads(events[0].render_event_pattern()),
            {'detail': {'eventName': ['CreateSubnet'],
                        'eventSource': ['ec2.amazonaws.com'],
                        'userIdentity': {'userName': [{'anything-but': 'deputy'}]}},
             'detail-type': ['AWS API Call via CloudTrail']})

    @functional
    def test_sqs_subscriber(self):
        session_factory = self.replay_flight_data('test_mu_sqs_subscriber')

        func_name = 'c7n-hello-sqs'
        queue_name = "my-dev-test-3"

        # Setup Queues
        session = session_factory()
        client = session.client('sqs')
        queue_url = client.create_queue(QueueName=queue_name).get('QueueUrl')
        queue_arn = client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['QueueArn'])['Attributes']['QueueArn']
        self.addCleanup(client.delete_queue, QueueUrl=queue_url)

        # Setup Function
        params = dict(
            session_factory=session_factory,
            name=func_name,
            role="arn:aws:iam::644160558196:role/custodian-mu",
            events=[SQSSubscription(session_factory, [queue_arn])])

        func = helloworld.get_function(**params)
        manager = LambdaManager(session_factory)
        manager.publish(func)
        self.addCleanup(manager.remove, func)

        # Send and Receive Check
        client.send_message(
            QueueUrl=queue_url, MessageBody=json.dumps({'jurassic': 'block'}))

        if self.recording:
            time.sleep(60)

#        log_events = list(manager.logs(func, "1970-1-1 UTC", "2037-1-1"))
#        messages = [
#            e["message"] for e in log_events if e["message"].startswith('{"Records')
#        ]
        self.addCleanup(
            session.client("logs").delete_log_group,
            logGroupName="/aws/lambda/%s" % func_name)
#        self.assertIn(
#            'jurassic',
#            json.loads(messages[0])["Records"][0]["body"])

    @functional
    def test_sns_subscriber_and_ipaddress(self):
        self.patch(SNSSubscription, "iam_delay", 0.01)
        session_factory = self.replay_flight_data("test_sns_subscriber_and_ipaddress")
        session = session_factory()
        client = session.client("sns")

        # create an sns topic
        tname = "custodian-test-sns-sub"
        topic_arn = client.create_topic(Name=tname)["TopicArn"]
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        # provision a lambda via mu
        params = dict(
            session_factory=session_factory,
            name="c7n-hello-world",
            role="arn:aws:iam::644160558196:role/custodian-mu",
            events=[SNSSubscription(session_factory, [topic_arn])],
        )

        func = helloworld.get_function(**params)
        manager = LambdaManager(session_factory)
        manager.publish(func)
        self.addCleanup(manager.remove, func)

        # now publish to the topic and look for lambda log output
        client.publish(TopicArn=topic_arn, Message="Greetings, program!")
        if self.recording:
            time.sleep(30)
#        log_events = manager.logs(func, "1970-1-1 UTC", "2037-1-1")
#        messages = [
#            e["message"] for e in log_events if e["message"].startswith('{"Records')
#        ]
#        self.addCleanup(
#            session.client("logs").delete_log_group,
#            logGroupName="/aws/lambda/c7n-hello-world",
#        )
#        self.assertEqual(
#            json.loads(messages[0])["Records"][0]["Sns"]["Message"],
#            "Greetings, program!",
#        )

    def test_cwe_update_config_and_code(self):
        # Originally this was testing the no update case.. but
        # That is tricky to record, any updates to the code end up
        # causing issues due to checksum mismatches which imply updating
        # the function code / which invalidate the recorded data and
        # the focus of the test.

        session_factory = self.replay_flight_data("test_cwe_update", zdata=True)
        p = self.load_policy({
            "resource": "s3",
            "name": "s3-bucket-policy",
            "mode": {"type": "cloudtrail",
                     "events": ["CreateBucket"], 'runtime': 'python3.12'},
            "filters": [
                {"type": "missing-policy-statement",
                 "statement_ids": ["RequireEncryptedPutObject"]},
            ],
            "actions": ["no-op"],
        })
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        result = mgr.publish(pl, "Dev", role=ROLE)
        self.addCleanup(mgr.remove, pl)

        p = self.load_policy(
            {
                "resource": "s3",
                "name": "s3-bucket-policy",
                "mode": {
                    "type": "cloudtrail",
                    "memory": 256,
                    'runtime': 'python3.12',
                    "events": [
                        "CreateBucket",
                        {
                            "event": "PutBucketPolicy",
                            "ids": "requestParameters.bucketName",
                            "source": "s3.amazonaws.com",
                        },
                    ],
                },
                "filters": [
                    {
                        "type": "missing-policy-statement",
                        "statement_ids": ["RequireEncryptedPutObject"],
                    }
                ],
                "actions": ["no-op"],
            },
        )

        output = self.capture_logging("custodian.serverless", level=logging.DEBUG)
        result2 = mgr.publish(PolicyLambda(p), "Dev", role=ROLE)

        lines = output.getvalue().strip().split("\n")
        self.assertTrue("Updating function custodian-s3-bucket-policy code" in lines)
        self.assertTrue(
            "Updating function: custodian-s3-bucket-policy config MemorySize" in lines)
        self.assertEqual(result["FunctionName"], result2["FunctionName"])
        # drive by coverage
        functions = [
            i
            for i in mgr.list_functions()
            if i["FunctionName"] == "custodian-s3-bucket-policy"
        ]
        self.assertEqual(len(functions), 1)

    def test_cwe_trail(self):
        session_factory = self.replay_flight_data("test_cwe_trail", zdata=True)
        p = self.load_policy({
            "resource": "s3",
            "name": "s3-bucket-policy",
            "mode": {"type": "cloudtrail", "events": ["CreateBucket"]},
            "filters": [
                {
                    "type": "missing-policy-statement",
                    "statement_ids": ["RequireEncryptedPutObject"],
                }
            ],
            "actions": ["no-op"]},
            session_factory=session_factory)

        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        self.addCleanup(mgr.remove, pl)
        result = mgr.publish(pl, "Dev", role=ROLE)

        events = pl.get_events(session_factory)
        self.assertEqual(len(events), 1)
        event = events.pop()
        self.assertEqual(
            json.loads(event.render_event_pattern()),
            {
                u"detail": {
                    u"eventName": [u"CreateBucket"],
                    u"eventSource": [u"s3.amazonaws.com"],
                },
                u"detail-type": ["AWS API Call via CloudTrail"],
            },
        )

        self.assert_items(
            result,
            {
                "Description": "cloud-custodian lambda policy",
                "FunctionName": "custodian-s3-bucket-policy",
                "Handler": "custodian_policy.run",
                "MemorySize": 512,
                "Runtime": "python2.7",
                "Timeout": 60,
            },
        )

    def test_cwe_instance(self):
        session_factory = self.replay_flight_data("test_cwe_instance", zdata=True)
        p = self.load_policy({
            "resource": "s3",
            "name": "ec2-encrypted-vol",
            "mode": {"type": "ec2-instance-state", "events": ["pending"]}},
            session_factory=session_factory)

        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        self.addCleanup(mgr.remove, pl)
        result = mgr.publish(pl, "Dev", role=ROLE)
        self.assert_items(
            result,
            {
                "Description": "cloud-custodian lambda policy",
                "FunctionName": "custodian-ec2-encrypted-vol",
                "Handler": "custodian_policy.run",
                "MemorySize": 512,
                "Runtime": "python2.7",
                "Timeout": 60,
            },
        )

        events = session_factory().client("events")
        result = events.list_rules(NamePrefix="custodian-ec2-encrypted-vol")
        self.assert_items(
            result["Rules"][0],
            {"State": "ENABLED", "Name": "custodian-ec2-encrypted-vol"},
        )

        self.assertEqual(
            json.loads(result["Rules"][0]["EventPattern"]),
            {
                "source": ["aws.ec2"],
                "detail": {"state": ["pending"]},
                "detail-type": ["EC2 Instance State-change Notification"],
            },
        )

    def test_cwe_asg_instance(self):
        session_factory = self.replay_flight_data("test_cwe_asg", zdata=True)
        p = self.load_policy(
            {
                "resource": "asg",
                "name": "asg-spin-detector",
                "mode": {"type": "asg-instance-state", "events": ["launch-failure"]},
            }, session_factory=session_factory)

        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        self.addCleanup(mgr.remove, pl)
        result = mgr.publish(pl, "Dev", role=ROLE)
        self.assert_items(
            result,
            {
                "FunctionName": "custodian-asg-spin-detector",
                "Handler": "custodian_policy.run",
                "MemorySize": 512,
                "Runtime": "python2.7",
                "Timeout": 60,
            },
        )

        events = session_factory().client("events")
        result = events.list_rules(NamePrefix="custodian-asg-spin-detector")
        self.assert_items(
            result["Rules"][0],
            {"State": "ENABLED", "Name": "custodian-asg-spin-detector"},
        )

        self.assertEqual(
            json.loads(result["Rules"][0]["EventPattern"]),
            {
                "source": ["aws.autoscaling"],
                "detail-type": ["EC2 Instance Launch Unsuccessful"],
            },
        )

    def test_cwe_security_hub_action(self):
        factory = self.replay_flight_data('test_mu_cwe_sechub_action')
        p = self.load_policy({
            'name': 'sechub',
            'resource': 'account',
            'mode': {
                'type': 'hub-action'}},
            session_factory=factory,
            config={'account_id': ACCOUNT_ID})
        mu_policy = PolicyLambda(p)
        events = mu_policy.get_events(factory)
        self.assertEqual(len(events), 1)
        hub_action = events.pop()
        self.assertEqual(
            json.loads(hub_action.cwe.render_event_pattern()),
            {'resources': [
                'arn:aws:securityhub:us-east-1:644160558196:action/custom/sechub'],
             'source': ['aws.securityhub'],
             'detail-type': [
                 'Security Hub Findings - Custom Action', 'Security Hub Insight Results'
            ]})

        hub_action.cwe = cwe = mock.Mock(CloudWatchEventSource)
        cwe.get.return_value = False
        cwe.update.return_value = True
        cwe.add.return_value = True

        self.assertEqual(repr(hub_action), "<SecurityHub Action sechub>")
        self.assertEqual(
            hub_action._get_arn(),
            "arn:aws:securityhub:us-east-1:644160558196:action/custom/sechub")
        self.assertEqual(
            hub_action.get(mu_policy.name), {'event': False, 'action': None})
        hub_action.add(mu_policy, None)
        self.assertEqual(
            {'event': False,
             'action': {
                 'ActionTargetArn': ('arn:aws:securityhub:us-east-1:'
                                     '644160558196:action/custom/sechub'),
                 'Name': 'Account sechub', 'Description': 'sechub'}},
            hub_action.get(mu_policy.name))
        hub_action.update(mu_policy)
        hub_action.remove(mu_policy, func_deleted=True)
        self.assertEqual(
            hub_action.get(mu_policy.name),
            {'event': False, 'action': None})

    def test_cwe_schedule(self):
        session_factory = self.replay_flight_data("test_cwe_schedule", zdata=True)
        p = self.load_policy(
            {
                "resource": "ec2",
                "name": "periodic-ec2-checker",
                "mode": {"type": "periodic", "schedule": "rate(1 day)"},
            }, session_factory=session_factory)

        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        self.addCleanup(mgr.remove, pl)
        result = mgr.publish(pl, "Dev", role=ROLE)
        self.assert_items(
            result,
            {
                "FunctionName": "custodian-periodic-ec2-checker",
                "Handler": "custodian_policy.run",
                "MemorySize": 512,
                "Runtime": "python2.7",
                "Timeout": 60,
            },
        )

        events = session_factory().client("events")
        result = events.list_rules(NamePrefix="custodian-periodic-ec2-checker")
        self.assert_items(
            result["Rules"][0],
            {
                "State": "ENABLED",
                "ScheduleExpression": "rate(1 day)",
                "Name": "custodian-periodic-ec2-checker",
            },
        )

    key_arn = "arn:aws:kms:us-west-2:644160558196:key/" "44d25a5c-7efa-44ed-8436-b9511ea921b3"
    sns_arn = "arn:aws:sns:us-west-2:644160558196:config-topic"

    def create_a_lambda(self, flight, **extra):
        session_factory = self.replay_flight_data(flight, zdata=True)
        mode = {
            "type": "config-rule", "role": "arn:aws:iam::644160558196:role/custodian-mu"
        }
        mode.update(extra)
        p = self.load_policy({
            "resource": "s3",
            "name": "hello-world",
            "actions": ["no-op"],
            "mode": mode},
            session_factory=session_factory)

        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)

        def cleanup():
            mgr.remove(pl)
            if self.recording:
                time.sleep(60)

        self.addCleanup(cleanup)
        return mgr, mgr.publish(pl)

    def test_eb_schedule(self):
        session_factory = self.replay_flight_data("test_eb_scheduler")
        scheduler_role = "arn:aws:iam::644160558196:role/custodian-scheduler-mu"
        policy = {
            "resource": "ec2",
            "name": "schedule-ec2-checker",
            "mode": {"type": "schedule", "schedule": "rate(1 day)",
                     "scheduler-role": scheduler_role},
        }
        p = self.load_policy(policy, session_factory=session_factory)

        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        self.addCleanup(mgr.remove, pl)
        result = mgr.publish(pl, "Dev", role=ROLE)
        self.assert_items(
            result,
            {
                "FunctionName": "custodian-schedule-ec2-checker",
                "Handler": "custodian_policy.run",
                "MemorySize": 512,
                "Runtime": "python3.11",
                "Timeout": 900,
            },
        )

        scheduler = session_factory().client("scheduler")
        result = scheduler.get_schedule(Name="custodian-schedule-ec2-checker")
        self.assert_items(
            result,
            {
                "State": "ENABLED",
                "ScheduleExpression": "rate(1 day)",
                "Name": "custodian-schedule-ec2-checker"
            }
        )
        self.assert_items(result['Target'], {"RoleArn": scheduler_role})
        # Verify Lambda ARN doesn't include version qualifier
        self.assertEqual(result['Target']['Arn'].count(':'), 6)

        # modify policy and re-publish
        policy['mode']['timezone'] = 'America/New_York'
        p = self.load_policy(policy, session_factory=session_factory)
        pl = PolicyLambda(p)
        self.addCleanup(mgr.remove, pl)
        result = mgr.publish(pl, "Dev", role=ROLE)
        result = scheduler.get_schedule(Name="custodian-schedule-ec2-checker")
        self.assert_items(
            result,
            {
                "State": "ENABLED",
                "ScheduleExpression": "rate(1 day)",
                "Name": "custodian-schedule-ec2-checker",
                "ScheduleExpressionTimezone": 'America/New_York'
            }
        )
        # Verify Lambda ARN still doesn't include version after code update
        self.assertEqual(result['Target']['Arn'].count(':'), 6)

        # modify scheduler role
        policy['mode']['scheduler-role'] = f'{scheduler_role}2'
        p = self.load_policy(policy, session_factory=session_factory)
        pl = PolicyLambda(p)
        self.addCleanup(mgr.remove, pl)
        result = mgr.publish(pl, "Dev", role=ROLE)
        result = scheduler.get_schedule(Name="custodian-schedule-ec2-checker")
        self.assert_items(result['Target'], {"RoleArn": f'{scheduler_role}2'})
        # Verify Lambda ARN still doesn't include version after code update
        self.assertEqual(result['Target']['Arn'].count(':'), 6)

    def test_pause_resume_sched_policy(self):
        session_factory = self.replay_flight_data("test_pause_resume_sched_policy")
        scheduler_role = "arn:aws:iam::644160558196:role/custodian-scheduler-mu"
        p = self.load_policy(
            {
                "resource": "ec2",
                "name": "schedule-ec2-checker-2",
                "mode": {"type": "schedule", "schedule": "rate(1 day)",
                         "scheduler-role": scheduler_role},
            },
            session_factory=session_factory)
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        self.addCleanup(mgr.remove, pl, True)
        mgr.publish(pl, "Dev", role=ROLE)
        events = pl.get_events(session_factory)
        self.assertEqual(len(events), 1)

        scheduler = session_factory().client('scheduler')
        events[0].pause(pl)
        schedule = scheduler.get_schedule(Name=pl.event_name)
        self.assertEqual(schedule["State"], "DISABLED")

        # subsequent calls to pause an already paused rule should be a no-op
        events[0].pause(pl)

        events[0].resume(pl)
        schedule = scheduler.get_schedule(Name=pl.event_name)
        self.assertEqual(schedule["State"], "ENABLED")

        # subsequent calls to resume an already enabled rule should be a no-op
        events[0].resume(pl)

    def create_a_lambda_with_lots_of_config(self, flight):
        extra = {
            "environment": {"Variables": {"FOO": "bar"}},
            "kms_key_arn": self.key_arn,
            "dead_letter_config": {"TargetArn": self.sns_arn},
            "tracing_config": {"Mode": "Active"},
            "tags": {"Foo": "Bar"},
        }
        return self.create_a_lambda(flight, **extra)

    def update_a_lambda(self, mgr, **config):
        mode = {
            "type": "config-rule", "role": "arn:aws:iam::644160558196:role/custodian-mu"
        }
        mode.update(config)
        p = self.load_policy({
            "resource": "s3",
            "name": "hello-world",
            "actions": ["no-op"],
            "mode": mode,
        })
        pl = PolicyLambda(p)
        return mgr.publish(pl)

    def test_config_coverage_for_lambda_creation(self):
        mgr, result = self.create_a_lambda_with_lots_of_config(
            "test_config_coverage_for_lambda_creation"
        )
        self.assert_items(
            result,
            {
                "Description": "cloud-custodian lambda policy",
                "FunctionName": "custodian-hello-world",
                "Handler": "custodian_policy.run",
                "MemorySize": 512,
                "Runtime": "python2.7",
                "Timeout": 60,
                "DeadLetterConfig": {"TargetArn": self.sns_arn},
                "Environment": {"Variables": {"FOO": "bar"}},
                "KMSKeyArn": self.key_arn,
                "TracingConfig": {"Mode": "Active"},
            },
        )
        tags = mgr.client.list_tags(Resource=result["FunctionArn"])["Tags"]
        self.assert_items(tags, {"Foo": "Bar"})

    def test_config_coverage_for_lambda_update_from_plain(self):
        mgr, result = self.create_a_lambda(
            "test_config_coverage_for_lambda_update_from_plain"
        )
        result = self.update_a_lambda(
            mgr,
            **{
                "environment": {"Variables": {"FOO": "bloo"}},
                "kms_key_arn": self.key_arn,
                "dead_letter_config": {"TargetArn": self.sns_arn},
                "tracing_config": {"Mode": "Active"},
                "tags": {"Foo": "Bloo"},
            }
        )

        self.assert_items(
            result,
            {
                "Description": "cloud-custodian lambda policy",
                "FunctionName": "custodian-hello-world",
                "Handler": "custodian_policy.run",
                "MemorySize": 512,
                "Runtime": "python2.7",
                "Timeout": 60,
                "DeadLetterConfig": {"TargetArn": self.sns_arn},
                "Environment": {"Variables": {"FOO": "bloo"}},
                "TracingConfig": {"Mode": "Active"},
            },
        )
        tags = mgr.client.list_tags(Resource=result["FunctionArn"])["Tags"]
        self.assert_items(tags, {"Foo": "Bloo"})

    def test_config_coverage_for_lambda_update_from_complex(self):
        mgr, result = self.create_a_lambda_with_lots_of_config(
            "test_config_coverage_for_lambda_update_from_complex"
        )
        result = self.update_a_lambda(
            mgr,
            **{
                "runtime": "python3.12",
                "environment": {"Variables": {"FOO": "baz"}},
                "kms_key_arn": "",
                "dead_letter_config": {},
                "tracing_config": {},
                "tags": {"Foo": "Baz", "Bah": "Bug"},
            }
        )

        self.assert_items(
            result,
            {
                "Description": "cloud-custodian lambda policy",
                "FunctionName": "custodian-hello-world",
                "Handler": "custodian_policy.run",
                "MemorySize": 512,
                "Runtime": "python3.12",
                "Timeout": 60,
                "DeadLetterConfig": {"TargetArn": self.sns_arn},
                "Environment": {"Variables": {"FOO": "baz"}},
                "TracingConfig": {"Mode": "Active"},
            },
        )
        tags = mgr.client.list_tags(Resource=result["FunctionArn"])["Tags"]
        self.assert_items(tags, {"Foo": "Baz", "Bah": "Bug"})

    def test_optional_packages(self):
        data = {
            "name": "s3-lambda-extra",
            "resource": "s3",
            "mode": {
                "type": "cloudtrail",
                "packages": ["boto3"],
                "events": ["CreateBucket"],
            },
        }
        p = self.load_policy(data)
        pl = PolicyLambda(p)
        pl.archive.close()
        self.assertTrue("boto3/utils.py" in pl.archive.get_filenames())

    def test_delta_config_diff(self):
        delta = LambdaManager.delta_function
        self.assertFalse(
            delta(
                {
                    "VpcConfig": {
                        "SubnetIds": ["s-1", "s-2"],
                        "SecurityGroupIds": ["sg-1", "sg-2"],
                    }
                },
                {
                    "VpcConfig": {
                        "SubnetIds": ["s-2", "s-1"],
                        "SecurityGroupIds": ["sg-2", "sg-1"],
                    }
                },
            )
        )
        self.assertTrue(
            delta(
                {
                    "VpcConfig": {
                        "SubnetIds": ["s-1", "s-2"],
                        "SecurityGroupIds": ["sg-1", "sg-2"],
                    }
                },
                {
                    "VpcConfig": {
                        "SubnetIds": ["s-2", "s-1"],
                        "SecurityGroupIds": ["sg-3", "sg-1"],
                    }
                },
            )
        )
        self.assertTrue(
            delta(
                {
                    "VpcConfig": {
                        "SubnetIds": ["s-1", "s-2"],
                        "SecurityGroupIds": ["sg-1", "sg-2"],
                    }
                },
                {
                    "VpcConfig": {
                        "SubnetIds": ["s-1", "s-2"],
                        "SecurityGroupIds": ["sg-1", "sg-2"],
                        "Ipv6AllowedForDualStack": True,
                    }
                },
            )
        )
        self.assertTrue(
            delta(
                {
                    "VpcConfig": {
                        "SubnetIds": ["s-1", "s-2"],
                        "SecurityGroupIds": ["sg-1", "sg-2"],
                        "VpcId": "vpc-12345",
                    }
                },
                {
                    "VpcConfig": {
                        "SubnetIds": ["s-1", "s-2"],
                        "SecurityGroupIds": ["sg-1", "sg-2"],
                        "VpcId": "vpc-23456",
                    }
                },
            )
        )
        self.assertFalse(delta({}, {"DeadLetterConfig": {}}))

        self.assertTrue(delta({}, {"DeadLetterConfig": {"TargetArn": "arn"}}))

        self.assertFalse(delta({}, {"Environment": {"Variables": {}}}))

        self.assertTrue(delta({}, {"Environment": {"Variables": {"k": "v"}}}))

        self.assertFalse(delta({}, {"KMSKeyArn": ""}))

        self.assertFalse(
            delta({}, {"VpcConfig": {"SecurityGroupIds": [], "SubnetIds": []}})
        )
        self.assertFalse(
            delta(
                {"VpcConfig": {
                    "SecurityGroupIds": [],
                    "SubnetIds": [],
                }},
                {"VpcConfig": {
                    "SecurityGroupIds": [],
                    "SubnetIds": [],
                    "VpcId": "",
                    "Ipv6AllowedForDualStack": False,
                }},
            )
        )

    def test_different_lambda_handler(self):
        p = PolicyLambda(Bag({"name": "hello", "data": {"mode": {"handler": "custom.handler"}}}))
        self.assertEqual(
            p.get_config()["Handler"],
            "custom.handler"
        )

    def test_config_defaults(self):
        p = PolicyLambda(Bag({"name": "hello", "data": {"mode": {}}}))
        self.maxDiff = None
        default_arch = platform.machine()
        if default_arch in ('aarch64', 'arm64'):
            default_arch = 'arm64'
        else:
            default_arch = 'x86_64'
        self.assertEqual(
            p.get_config(),
            {
                "DeadLetterConfig": {},
                "Description": "cloud-custodian lambda policy",
                "FunctionName": "custodian-hello",
                "Handler": "custodian_policy.run",
                "KMSKeyArn": "",
                "MemorySize": 512,
                "Role": "",
                "Runtime": "python3.11",
                "Architectures": [default_arch],
                "Tags": {},
                "Timeout": 900,
                "TracingConfig": {"Mode": "PassThrough"},
                "VpcConfig": {"SecurityGroupIds": [], "SubnetIds": []},
            },
        )

    def test_lambda_architecture(self):
        p = PolicyLambda(Bag({"name": "hello", "data": {"mode": {}}}))
        with patch('platform.machine', return_value='arm64'):
            self.assertEqual(
                p.get_config(),
                {
                    "DeadLetterConfig": {},
                    "Description": "cloud-custodian lambda policy",
                    "FunctionName": "custodian-hello",
                    "Handler": "custodian_policy.run",
                    "KMSKeyArn": "",
                    "MemorySize": 512,
                    "Role": "",
                    "Runtime": "python3.11",
                    "Architectures": ["arm64"],
                    "Tags": {},
                    "Timeout": 900,
                    "TracingConfig": {"Mode": "PassThrough"},
                    "VpcConfig": {"SecurityGroupIds": [], "SubnetIds": []},
                },
            )
        with patch('platform.machine', return_value='x86_64'):
            self.assertEqual(
                p.get_config(),
                {
                    "DeadLetterConfig": {},
                    "Description": "cloud-custodian lambda policy",
                    "FunctionName": "custodian-hello",
                    "Handler": "custodian_policy.run",
                    "KMSKeyArn": "",
                    "MemorySize": 512,
                    "Role": "",
                    "Runtime": "python3.11",
                    "Architectures": ["x86_64"],
                    "Tags": {},
                    "Timeout": 900,
                    "TracingConfig": {"Mode": "PassThrough"},
                    "VpcConfig": {"SecurityGroupIds": [], "SubnetIds": []},
                },
            )

    def test_remove_permissions_from_event_cloudtrail(self):
        session_factory = self.replay_flight_data("test_remove_permissions_event")
        p = self.load_policy({
            "resource": "ec2",
            "name": "test",
            "mode": {"type": "cloudtrail", "events": ["RunInstances"]}},
            session_factory=session_factory)
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        self.addCleanup(mgr.remove, pl, True)
        mgr.publish(pl, "Dev", role=ROLE)
        events = pl.get_events(session_factory)

        lambda_client = session_factory().client("lambda")
        policy = lambda_client.get_policy(FunctionName="custodian-test")
        self.assertTrue(policy)
        self.assertTrue(len(events) > 0)

        for e in events:
            e.remove(pl, func_deleted=False)

        with self.assertRaises(lambda_client.exceptions.ResourceNotFoundException):
            lambda_client.get_policy(FunctionName="custodian-test")

        # we should be able to call the remove again even tho it's already gone
        for e in events:
            e.remove(pl, func_deleted=False)

        # we should also be able to explicitly remove_permissions even though it's
        # already gone
        for e in events:
            e.remove_permissions(pl, remove_permission=True)

    def test_pause_resume_policy(self):
        session_factory = self.replay_flight_data("test_pause_resume_policy")
        p = self.load_policy({
            "resource": "ec2",
            "name": "test",
            "mode": {"type": "cloudtrail", "events": ["RunInstances"]}},
            session_factory=session_factory)
        pl = PolicyLambda(p)
        mgr = LambdaManager(session_factory)
        self.addCleanup(mgr.remove, pl, True)
        mgr.publish(pl, "Dev", role=ROLE)
        events = pl.get_events(session_factory)
        self.assertEqual(len(events), 1)

        cw_client = session_factory().client('events')

        events[0].pause(pl)
        rule = cw_client.describe_rule(Name=pl.event_name)
        self.assertEqual(rule["State"], "DISABLED")

        # subsequent calls to pause an already paused rule should be a no-op
        events[0].pause(pl)

        events[0].resume(pl)
        rule = cw_client.describe_rule(Name=pl.event_name)
        self.assertEqual(rule["State"], "ENABLED")

        # subsequent calls to resume an already enabled rule should be a no-op
        events[0].resume(pl)

    def test_cloudwatch_log_subscription(self):
        session_factory = self.replay_flight_data("test_cloudwatch_log_subscription")
        func = self.make_func(role=ROLE)
        LambdaManager(session_factory).publish(func)
        cwls = CloudWatchLogSubscription(
            session_factory,
            [
                {
                    "logGroupName": "/aws/lambda/test",
                    "arn": "arn:aws:logs:us-east-1:644160558196:log-group:/aws/lambda/test:*",
                }
            ],
            "foo"
        )
        cwls.add(func, None)
        lambda_client = session_factory().client("lambda")
        policy = lambda_client.get_policy(FunctionName="test-foo-bar")
        self.assertTrue(policy)

        cwls.remove(func, func_deleted=False)
        with self.assertRaises(lambda_client.exceptions.ResourceNotFoundException):
            lambda_client.get_policy(FunctionName="test-foo-bar")

    def test_sns_subscription_remove_permission_idempotent(self):
        session_factory = self.replay_flight_data(
            "test_sns_subscription_remove_permission_idempotent"
        )
        func = self.make_func(role=ROLE, runtime="python3.9")
        mgr = LambdaManager(session_factory)

        mgr.publish(func)

        sns_sub = SNSSubscription(
            session_factory,
            topic_arns=["arn:aws:sns:us-east-1:644160558196:test-topic"]
        )
        # this shouldn't raise an exception even though we never added it
        sns_sub.remove(func, func_deleted=False)

        # verify the permissions are not there
        lambda_client = session_factory().client("lambda")
        found_function = lambda_client.get_function(FunctionName="test-foo-bar")
        self.assertTrue(found_function)
        with self.assertRaises(lambda_client.exceptions.ResourceNotFoundException):
            lambda_client.get_policy(FunctionName="test-foo-bar")

    def test_s3_bucket_lambda_notification_remove_idempotent(self):
        session_factory = self.replay_flight_data(
            "test_s3_bucket_lambda_notification_remove_idempotent"
        )
        func = self.make_func(role=ROLE, runtime="python3.9")
        mgr = LambdaManager(session_factory)
        self.addCleanup(mgr.remove, func, True)

        mgr.publish(func)

        bln = BucketLambdaNotification(
            data={},
            session_factory=session_factory,
            bucket={"Name": "c7n-ci20210930214353595400000001"}
        )

        bln.add(func, None)
        bln.remove(func, func_deleted=False)

        # we should be able to do idempotent removal
        bln.remove(func, func_deleted=False)

        # verify the permissions are gone
        lambda_client = session_factory().client("lambda")
        found_function = lambda_client.get_function(FunctionName="test-foo-bar")
        self.assertTrue(found_function)
        with self.assertRaises(lambda_client.exceptions.ResourceNotFoundException):
            lambda_client.get_policy(FunctionName="test-foo-bar")

    def test_publishes_a_lambda(self):
        session_factory = self.replay_flight_data("test_publishes_a_lambda")
        mgr = LambdaManager(session_factory)
        func = self.make_func()
        self.addCleanup(mgr.remove, func)
        result = mgr.publish(func)
        self.assertEqual(result["CodeSize"], 169)

    def test_publish_a_lambda_with_layer_and_concurrency(self):
        factory = self.replay_flight_data('test_lambda_layer_concurrent_publish')
        mgr = LambdaManager(factory)
        layers = ['arn:aws:lambda:us-east-1:644160558196:layer:AWSLambdaPowertoolsPythonV2:59']
        func = self.make_func(
            concurrency=5,
            layers=layers)
        self.addCleanup(mgr.remove, func)

        result = mgr.publish(func)
        self.assertEqual(result['Layers'][0]['Arn'], layers[0])
        if self.recording:
            time.sleep(10)
        published = mgr.get(func.name)
        self.assertEqual(published['Concurrency']['ReservedConcurrentExecutions'], 5)

        func = self.make_func(layers=layers)
        output = self.capture_logging("custodian.serverless", level=logging.DEBUG)
        result = mgr.publish(func)
        self.assertEqual(result['Layers'][0]['Arn'], layers[0])

        lines = output.getvalue().strip().split("\n")
        self.assertFalse('Updating function: test-foo-bar config Layers' in lines)
        self.assertTrue('Removing function: test-foo-bar concurrency' in lines)

    def test_can_switch_runtimes(self):
        session_factory = self.replay_flight_data("test_can_switch_runtimes")
        func = self.make_func()
        mgr = LambdaManager(session_factory)
        self.addCleanup(mgr.remove, func)
        result = mgr.publish(func)
        self.assertEqual(result["Runtime"], "python2.7")

        func.func_data["runtime"] = "python3.6"
        result = mgr.publish(func)
        self.assertEqual(result["Runtime"], "python3.6")


class PythonArchiveTest(unittest.TestCase):

    def make_archive(self, modules=(), cache_file=None):
        archive = self.make_open_archive(modules, cache_file=cache_file)
        archive.close()
        return archive

    def make_open_archive(self, modules=(), cache_file=None):
        archive = PythonPackageArchive(modules=modules, cache_file=cache_file)
        self.addCleanup(archive.remove)
        return archive

    def get_filenames(self, modules=()):
        return self.make_archive(modules).get_filenames()

    def test_handles_stdlib_modules(self):
        filenames = self.get_filenames(["webbrowser"])
        self.assertTrue("webbrowser.py" in filenames)

    def test_handles_third_party_modules(self):
        filenames = self.get_filenames(["botocore"])
        self.assertTrue("botocore/__init__.py" in filenames)

    def test_handles_packages(self):
        filenames = self.get_filenames(["c7n"])
        self.assertTrue("c7n/__init__.py" in filenames)
        self.assertTrue("c7n/resources/s3.py" in filenames)
        self.assertTrue("c7n/ufuncs/s3crypt.py" in filenames)

    def _install_namespace_package(self, tmp_sitedir):
        # Install our test namespace package in such a way that both py27 and
        # py36 can find it.
        from setuptools import namespaces

        installer = namespaces.Installer()

        class Distribution:
            namespace_packages = ["namespace_package"]

        installer.distribution = Distribution()
        installer.target = os.path.join(tmp_sitedir, "namespace_package.pth")
        installer.outputs = []
        installer.dry_run = False
        installer.install_namespaces()
        site.addsitedir(tmp_sitedir, known_paths=site._init_pathinfo())

    def test_handles_namespace_packages(self):
        bench = tempfile.mkdtemp()

        def cleanup():
            while bench in sys.path:
                sys.path.remove(bench)
            shutil.rmtree(bench)

        self.addCleanup(cleanup)

        subpackage = os.path.join(bench, "namespace_package", "subpackage")
        os.makedirs(subpackage)
        open(os.path.join(subpackage, "__init__.py"), "w+").write("foo = 42\n")

        def _():
            from namespace_package.subpackage import foo

            assert foo  # dodge linter

        self.assertRaises(ImportError, _)

        self._install_namespace_package(bench)

        from namespace_package.subpackage import foo

        self.assertEqual(foo, 42)

        filenames = self.get_filenames(["namespace_package"])
        self.assertTrue("namespace_package/__init__.py" not in filenames)
        self.assertTrue("namespace_package/subpackage/__init__.py" in filenames)
        self.assertTrue(filenames[-1].endswith("-nspkg.pth"))

    def test_excludes_non_py_files(self):
        filenames = self.get_filenames(["ctypes"])
        self.assertTrue("README.ctypes" not in filenames)

    def test_cant_get_bytes_when_open(self):
        archive = self.make_open_archive()
        self.assertRaises(AssertionError, archive.get_bytes)

    def test_cant_add_files_when_closed(self):
        archive = self.make_archive()
        self.assertRaises(AssertionError, archive.add_file, __file__)

    def test_cant_add_contents_when_closed(self):
        archive = self.make_archive()
        self.assertRaises(AssertionError, archive.add_contents, "foo", "bar")

    def test_can_add_additional_files_while_open(self):
        archive = self.make_open_archive()
        archive.add_file(__file__)
        archive.close()
        filenames = archive.get_filenames()
        self.assertTrue(os.path.basename(__file__) in filenames)

    def test_can_set_path_when_adding_files(self):
        archive = self.make_open_archive()
        archive.add_file(__file__, "cheese/is/yummy.txt")
        archive.close()
        filenames = archive.get_filenames()
        self.assertTrue(os.path.basename(__file__) not in filenames)
        self.assertTrue("cheese/is/yummy.txt" in filenames)

    def test_can_add_a_file_with_contents_from_a_string(self):
        archive = self.make_open_archive()
        archive.add_contents("cheese.txt", "So yummy!")
        archive.close()
        self.assertTrue("cheese.txt" in archive.get_filenames())
        with archive.get_reader() as reader:
            self.assertEqual(b"So yummy!", reader.read("cheese.txt"))

    def test_custodian_archive_creates_a_custodian_archive(self):
        archive = custodian_archive()
        self.addCleanup(archive.remove)
        archive.close()
        filenames = archive.get_filenames()
        self.assertTrue("c7n/__init__.py" in filenames)

    def make_file(self):
        bench = tempfile.mkdtemp()
        path = os.path.join(bench, "foo.txt")
        open(path, "w+").write("Foo.")
        self.addCleanup(lambda: shutil.rmtree(bench))
        return path

    def check_world_readable(self, archive):
        world_readable = 0o004 << 16
        for info in zipfile.ZipFile(archive.path).filelist:
            self.assertEqual(info.external_attr & world_readable, world_readable)

    def test_files_are_all_readable(self):
        self.check_world_readable(self.make_archive(["c7n"]))

    def test_even_unreadable_files_become_readable(self):
        path = self.make_file()
        os.chmod(path, 0o600)
        archive = self.make_open_archive()
        archive.add_file(path)
        archive.close()
        self.check_world_readable(archive)

    def test_unless_you_make_your_own_zipinfo(self):
        info = zipfile.ZipInfo(self.make_file())
        archive = self.make_open_archive()
        archive.add_contents(info, "foo.txt")
        archive.close()
        self.assertRaises(AssertionError, self.check_world_readable, archive)

    def test_cache_zip_file(self):
        archive = self.make_archive(cache_file=os.path.join(os.path.dirname(__file__),
                                                            "data",
                                                            "test.zip"))

        self.assertTrue("cheese.txt" in archive.get_filenames())
        self.assertTrue("cheese/is/yummy.txt" in archive.get_filenames())
        with archive.get_reader() as reader:
            self.assertEqual(b"So yummy!", reader.read("cheese.txt"))
            self.assertEqual(b"True!", reader.read("cheese/is/yummy.txt"))


class PycCase(unittest.TestCase):

    def setUp(self):
        self.bench = tempfile.mkdtemp()
        sys.path.insert(0, self.bench)

    def tearDown(self):
        sys.path.remove(self.bench)
        shutil.rmtree(self.bench)

    def py_with_pyc(self, name):
        path = os.path.join(self.bench, name)
        with open(path, "w+") as fp:
            fp.write("42")
        py_compile.compile(path)
        return path


class Constructor(PycCase):

    def test_class_constructor_only_accepts_py_modules_not_pyc(self):

        # Create a module with both *.py and *.pyc.
        self.py_with_pyc("foo.py")

        # Create another with a *.pyc but no *.py behind it.
        os.unlink(self.py_with_pyc("bar.py"))

        # Now: *.py takes precedence over *.pyc ...
        def get(name):
            return os.path.basename(importlib.import_module(name).__file__)

        self.assertTrue(get("foo"), "foo.py")
        try:
            # ... and while *.pyc is importable ...
            self.assertTrue(get("bar"), "bar.pyc")
        except ImportError:
            try:
                # (except on PyPy)
                # http://doc.pypy.org/en/latest/config/objspace.lonepycfiles.html
                self.assertEqual(platform.python_implementation(), "PyPy")
            except AssertionError:
                # (... aaaaaand Python 3)
                self.assertEqual(platform.python_version_tuple()[0], "3")
        else:
            # ... we refuse it.
            with self.assertRaises(ValueError) as raised:
                PythonPackageArchive(modules=["bar"])
            msg = raised.exception.args[0]
            self.assertTrue(msg.startswith("Could not find a *.py source file"))
            self.assertTrue(msg.endswith("bar.pyc"))

        # We readily ignore a *.pyc if a *.py exists.
        archive = PythonPackageArchive(modules=["foo"])
        archive.close()
        self.assertEqual(archive.get_filenames(), ["foo.py"])
        with archive.get_reader() as reader:
            self.assertEqual(b"42", reader.read("foo.py"))


class AddPyFile(PycCase):

    def test_can_add_py_file(self):
        archive = PythonPackageArchive()
        archive.add_py_file(self.py_with_pyc("foo.py"))
        archive.close()
        self.assertEqual(archive.get_filenames(), ["foo.py"])

    def test_reverts_to_py_if_available(self):
        archive = PythonPackageArchive()
        py = self.py_with_pyc("foo.py")
        archive.add_py_file(py + "c")
        archive.close()
        self.assertEqual(archive.get_filenames(), ["foo.py"])

    def test_fails_if_py_not_available(self):
        archive = PythonPackageArchive()
        py = self.py_with_pyc("foo.py")
        os.unlink(py)
        self.assertRaises(IOError, archive.add_py_file, py + "c")


class DiffTags(unittest.TestCase):

    def test_empty(self):
        assert LambdaManager.diff_tags({}, {}) == ({}, [])

    def test_removal(self):
        assert LambdaManager.diff_tags({"Foo": "Bar"}, {}) == ({}, ["Foo"])

    def test_addition(self):
        assert LambdaManager.diff_tags({}, {"Foo": "Bar"}) == ({"Foo": "Bar"}, [])

    def test_update(self):
        assert LambdaManager.diff_tags(
            {"Foo": "Bar"}, {"Foo": "Baz"}) == ({"Foo": "Baz"}, [])
