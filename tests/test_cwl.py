# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

from c7n.resources.cw import LogMetricAlarmFilter
from .common import BaseTest, functional
from unittest.mock import MagicMock

from pytest_terraform import terraform


@terraform('log_delete', teardown=terraform.TEARDOWN_IGNORE)
def test_tagged_log_group_delete(test, log_delete):
    factory = test.replay_flight_data(
        'test_log_group_tag_delete', region="us-west-2")

    p = test.load_policy({
        'name': 'group-delete',
        'resource': 'aws.log-group',
        'filters': [{
            'tag:App': 'Foie'}],
        'actions': ['delete']},
        session_factory=factory, config={'region': 'us-west-2'})

    resources = p.run()
    assert len(resources) == 1
    assert resources[0]['logGroupName'] == log_delete[
        'aws_cloudwatch_log_group.test_group.name']
    client = factory().client('logs')
    assert client.describe_log_groups(
        logGroupNamePrefix=resources[0]['logGroupName']).get(
            'logGroups') == []


class LogGroupTest(BaseTest):

    def test_cross_account(self):
        factory = self.replay_flight_data("test_log_group_cross_account")
        p = self.load_policy(
            {
                "name": "cross-log",
                "resource": "log-group",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:CrossAccountViolations"], ["1111111111111"])

    def test_kms_filter(self):
        session_factory = self.replay_flight_data('test_log_group_kms_filter')
        kms = session_factory().client('kms')
        p = self.load_policy(
            {
                'name': 'test-log-group-kms-filter',
                'resource': 'log-group',
                'filters': [
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/cw'
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(len(resources), 1)
        aliases = kms.list_aliases(KeyId=resources[0]['kmsKeyId'])
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/cw')

    def test_subscription_filter(self):
        factory = self.replay_flight_data("test_log_group_subscription_filter")
        p = self.load_policy(
            {
                "name": "subscription-filter",
                "resource": "log-group",
                "filters": [{"type": "subscription-filter"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:SubscriptionFilters"][0]["destinationArn"],
            "arn:aws:lambda:us-east-2:1111111111111:function:CloudCustodian")

    def test_age_normalize(self):
        factory = self.replay_flight_data("test_log_group_age_normalize")
        p = self.load_policy({
            'name': 'log-age',
            'resource': 'aws.log-group',
            'filters': [{
                'type': 'value',
                'value_type': 'age',
                'value': 30,
                'op': 'greater-than',
                'key': 'creationTime'}]},
            session_factory=factory, config={'region': 'us-west-2'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['creationTime'], 1548368507441)

    def test_last_write(self):
        log_group = "test-log-group"
        log_stream = "stream1"
        factory = self.replay_flight_data("test_log_group_last_write")
        if self.recording:
            client = factory().client("logs")
            client.create_log_group(logGroupName=log_group)
            self.addCleanup(client.delete_log_group, logGroupName=log_group)
            time.sleep(5)
            client.create_log_stream(logGroupName=log_group, logStreamName=log_stream)
            time.sleep(5)
            client.put_log_events(
                logGroupName=log_group,
                logStreamName=log_stream,
                logEvents=[
                    {
                        'timestamp': int(time.time() * 1000),
                        'message': 'message 1'
                    }
                ]
            )
            time.sleep(5)

        p = self.load_policy(
            {
                "name": "test-last-write",
                "resource": "log-group",
                "filters": [
                    {"logGroupName": log_group},
                    {"type": "last-write", "days": 0},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["logGroupName"], log_group)
        # should match lastIngestionTime on first stream
        self.assertEqual(
            resources[0]["lastWrite"].timestamp() * 1000,
            float(resources[0]["streams"][0]["lastIngestionTime"])
        )
        self.assertNotEqual(
            resources[0]["lastWrite"].timestamp() * 1000,
            float(resources[0]["creationTime"])
        )
        self.assertGreater(resources[0]["lastWrite"].year, 2019)

    def test_last_write_no_streams(self):
        log_group = "test-log-group"
        factory = self.replay_flight_data("test_log_group_last_write_no_streams")
        if self.recording:
            client = factory().client("logs")
            client.create_log_group(logGroupName=log_group)
            self.addCleanup(client.delete_log_group, logGroupName=log_group)

        p = self.load_policy(
            {
                "name": "test-last-write",
                "resource": "log-group",
                "filters": [
                    {"logGroupName": log_group},
                    {"type": "last-write", "days": 0},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["logGroupName"], log_group)
        # should match CreationTime on group itself
        self.assertEqual(
            resources[0]["lastWrite"].timestamp() * 1000,
            float(resources[0]["creationTime"])
        )
        self.assertGreater(resources[0]["lastWrite"].year, 2019)

    def test_last_write_empty_streams(self):
        log_group = "test-log-group"
        log_stream = "stream1"
        factory = self.replay_flight_data("test_log_group_last_write_empty_streams")
        if self.recording:
            client = factory().client("logs")
            client.create_log_group(logGroupName=log_group)
            self.addCleanup(client.delete_log_group, logGroupName=log_group)
            time.sleep(5)
            client.create_log_stream(logGroupName=log_group, logStreamName=log_stream)

        p = self.load_policy(
            {
                "name": "test-last-write",
                "resource": "log-group",
                "filters": [
                    {"logGroupName": log_group},
                    {"type": "last-write", "days": 0},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["logGroupName"], log_group)
        # should match CreationTime on latest stream
        self.assertEqual(
            resources[0]["lastWrite"].timestamp() * 1000,
            float(resources[0]["streams"][0]["creationTime"])
        )
        self.assertNotEqual(
            resources[0]["lastWrite"].timestamp() * 1000,
            float(resources[0]["creationTime"])
        )
        self.assertGreater(resources[0]["lastWrite"].year, 2019)

    @functional
    def test_retention(self):
        log_group = "c7n-test-a"
        factory = self.replay_flight_data("test_log_group_retention")
        client = factory().client("logs")
        client.create_log_group(logGroupName=log_group)
        self.addCleanup(client.delete_log_group, logGroupName=log_group)
        p = self.load_policy(
            {
                "name": "set-retention",
                "resource": "log-group",
                "filters": [{"logGroupName": log_group}],
                "actions": [{"type": "retention", "days": 14}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            client.describe_log_groups(logGroupNamePrefix=log_group)["logGroups"][0][
                "retentionInDays"
            ],
            14,
        )

    def test_log_group_delete_error(self):
        factory = self.replay_flight_data("test_log_group_delete")
        client = factory().client("logs")
        mock_factory = MagicMock()
        mock_factory.region = 'us-east-1'
        mock_factory().client(
            'logs').exceptions.ResourceNotFoundException = (
                client.exceptions.ResourceNotFoundException)
        mock_factory().client('logs').delete_log_group.side_effect = (
            client.exceptions.ResourceNotFoundException(
                {'Error': {'Code': 'xyz'}},
                operation_name='delete_log_group'))
        p = self.load_policy({
            'name': 'delete-log-err',
            'resource': 'log-group',
            'actions': ['delete']},
            session_factory=mock_factory)

        try:
            p.resource_manager.actions[0].process(
                [{'logGroupName': 'abc'}])
        except client.exceptions.ResourceNotFoundException:
            self.fail('should not raise')
        mock_factory().client('logs').delete_log_group.assert_called_once()

    @functional
    def test_delete(self):
        log_group = "c7n-test-b"
        factory = self.replay_flight_data("test_log_group_delete")
        client = factory().client("logs")
        client.create_log_group(logGroupName=log_group)

        p = self.load_policy(
            {
                "name": "delete-log-group",
                "resource": "log-group",
                "filters": [{"logGroupName": log_group}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["logGroupName"], log_group)
        self.assertEqual(client.describe_log_groups(
            logGroupNamePrefix=log_group)['logGroups'], [])

    @functional
    def test_encrypt(self):
        log_group = 'c7n-encrypted'
        session_factory = self.replay_flight_data('test_log_group_encrypt')
        client = session_factory(region='us-west-2').client('logs')
        client.create_log_group(logGroupName=log_group)
        self.addCleanup(client.delete_log_group, logGroupName=log_group)

        p = self.load_policy(
            {'name': 'encrypt-log-group',
             'resource': 'log-group',
             'filters': [{'logGroupName': log_group}],
             'actions': [{
                 'type': 'set-encryption',
                 'kms-key': 'alias/app-logs'}]},
            config={'region': 'us-west-2'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['logGroupName'], log_group)
        results = client.describe_log_groups(
            logGroupNamePrefix=log_group)['logGroups']
        self.assertEqual(
            results[0]['kmsKeyId'],
            'arn:aws:kms:us-west-2:644160558196:key/6f13fc53-8da0-46f2-9c69-c1f9fbf471d7')

    def test_metrics(self):
        session_factory = self.replay_flight_data('test_log_group_metric')
        p = self.load_policy(
            {'name': 'metric-log-group',
             'resource': 'log-group',
             'filters': [
                 {"logGroupName": "/aws/lambda/myIOTFunction"},
                 {"type": "metrics",
                  "name": "IncomingBytes",
                  "value": 1,
                  "op": "greater-than"}]},
            config={'region': 'us-west-2'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn('c7n.metrics', resources[0])

    def test_log_metric_filter(self):
        session_factory = self.replay_flight_data('test_log_group_log_metric_filter')
        p = self.load_policy(
            {"name": "log-metric",
             "resource": "aws.log-metric",
             "filters": [
                 {"type": "value",
                  "key": "logGroupName",
                  "value": "metric-filter-test1"}]},
            config={'region': 'us-east-2'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_log_metric_filter_alarm(self):
        session_factory = self.replay_flight_data('test_log_group_log_metric_filter_alarm')
        p = self.load_policy(
            {"name": "log-metric",
             "resource": "aws.log-metric",
             "filters": [
                 {"type": "value",
                  "key": "logGroupName",
                  "value": "metric-filter-test*",
                  "op": "glob"},
                 {"type": "alarm",
                  "key": "AlarmName",
                  "value": "present"}]},
            config={'region': 'us-east-2'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertIn('c7n:MetricAlarms', resources[0])

        # Ensure matching test results whether we fetch alarms
        # individually or in bulk
        LogMetricAlarmFilter.FetchThreshold = 0
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertIn('c7n:MetricAlarms', resources[0])


@terraform('copy_lambda_tags_to_log_group')
def test_copy_lambda_tags_to_log_group(test, copy_lambda_tags_to_log_group):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data(
        'test_copy_lambda_tags_to_log_group', region=aws_region)

    log_group_name = copy_lambda_tags_to_log_group['aws_cloudwatch_log_group.this.name']
    lambda_tags = copy_lambda_tags_to_log_group[
        'aws_lambda_function.this.tags']
    copy_tag1_value = lambda_tags['copy_tag1']
    copy_tag2_value = lambda_tags['copy_tag2']

    assert 'non_existing_lambda_tag' not in lambda_tags

    p = test.load_policy(
        {
            'name': 'cloudwatch-aws-service-log-groups',
            'resource': 'aws.log-group',
            'filters': [
                {
                    'type': 'value',
                    'key': 'logGroupName',
                    'op': 'eq',
                    'value': log_group_name
                }
            ],
            'actions': [
                {
                    'type': 'copy-aws-service-tags',
                    'services': ['lambda'],
                    'tags': [
                        'copy_tag1',
                        'copy_tag2',
                        'non_existing_lambda_tag',
                    ]
                }
            ]
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    assert len(resources) == 1

    client = session_factory().client('logs')
    log_group_tags = client.list_tags_log_group(logGroupName=log_group_name)
    assert len(log_group_tags) == 2
    assert log_group_tags['tags']['copy_tag1'] == copy_tag1_value
    assert log_group_tags['tags']['copy_tag2'] == copy_tag2_value
    assert 'non_existing_lambda_tag' not in log_group_tags['tags']


@terraform('copy_lambda_tags_to_log_group_skip_existing_tags')
def test_copy_lambda_tags_to_log_group_skip_existing_tags(
    test,
    copy_lambda_tags_to_log_group_skip_existing_tags
):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data(
        'test_copy_lambda_tags_to_log_group_skip_existing_tags',
        region=aws_region
    )

    log_group_name = copy_lambda_tags_to_log_group_skip_existing_tags[
        'aws_cloudwatch_log_group.this.name']
    log_group_existing_tag_value = copy_lambda_tags_to_log_group_skip_existing_tags[
        'aws_cloudwatch_log_group.this.tags.existing_tag']
    lambda_tags = copy_lambda_tags_to_log_group_skip_existing_tags[
        'aws_lambda_function.this.tags']
    copy_tag1_value = lambda_tags['copy_tag1']
    lambda_existing_tag_value = lambda_tags['existing_tag']

    p = test.load_policy(
        {
            'name': 'cloudwatch-aws-service-log-groups',
            'resource': 'aws.log-group',
            'filters': [
                {
                    'type': 'value',
                    'key': 'logGroupName',
                    'op': 'eq',
                    'value': log_group_name
                }
            ],
            'actions': [
                {
                    'type': 'copy-aws-service-tags',
                    'services': ['lambda'],
                    'skip_existing_tags': True,
                    'tags': [
                        'existing_tag',
                        'copy_tag1',
                    ]
                }
            ]
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    assert len(resources) == 1

    client = session_factory().client('logs')
    log_group_tags = client.list_tags_log_group(logGroupName=log_group_name)
    assert len(log_group_tags) == 2
    assert log_group_tags['tags']['existing_tag'] != lambda_existing_tag_value
    assert log_group_tags['tags']['existing_tag'] == log_group_existing_tag_value
    assert log_group_tags['tags']['copy_tag1'] == copy_tag1_value


@terraform('copy_lambda_tags_to_log_group_do_not_skip_existing_tags')
def test_copy_lambda_tags_to_log_group_do_not_skip_existing_tags(
    test,
    copy_lambda_tags_to_log_group_do_not_skip_existing_tags
):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data(
        'test_copy_lambda_tags_to_log_group_do_not_skip_existing_tags',
        region=aws_region
    )

    log_group_name = copy_lambda_tags_to_log_group_do_not_skip_existing_tags[
        'aws_cloudwatch_log_group.this.name']
    log_group_existing_tag_value = copy_lambda_tags_to_log_group_do_not_skip_existing_tags[
        'aws_cloudwatch_log_group.this.tags.existing_tag']
    lambda_tags = copy_lambda_tags_to_log_group_do_not_skip_existing_tags[
        'aws_lambda_function.this.tags']
    copy_tag1_value = lambda_tags['copy_tag1']
    lambda_existing_tag_value = lambda_tags['existing_tag']

    p = test.load_policy(
        {
            'name': 'cloudwatch-aws-service-log-groups',
            'resource': 'aws.log-group',
            'filters': [
                {
                    'type': 'value',
                    'key': 'logGroupName',
                    'op': 'eq',
                    'value': log_group_name
                }
            ],
            'actions': [
                {
                    'type': 'copy-aws-service-tags',
                    'services': ['lambda'],
                    'skip_existing_tags': False,
                    'tags': [
                        'existing_tag',
                        'copy_tag1',
                    ]
                }
            ]
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    assert len(resources) == 1

    client = session_factory().client('logs')
    log_group_tags = client.list_tags_log_group(logGroupName=log_group_name)
    assert len(log_group_tags) == 2
    assert log_group_tags['tags']['existing_tag'] != log_group_existing_tag_value
    assert log_group_tags['tags']['existing_tag'] == lambda_existing_tag_value
    assert log_group_tags['tags']['copy_tag1'] == copy_tag1_value


@terraform('copy_codebuild_tags_to_log_group')
def test_copy_codebuild_tags_to_log_group(test, copy_codebuild_tags_to_log_group):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data(
        'test_copy_codebuild_tags_to_log_group', region=aws_region)

    log_group_name = copy_codebuild_tags_to_log_group['aws_cloudwatch_log_group.this.name']
    codebuild_tags = copy_codebuild_tags_to_log_group[
        'aws_codebuild_project.this.tags']
    copy_tag1_value = codebuild_tags['copy_tag1']
    copy_tag2_value = codebuild_tags['copy_tag2']

    assert 'non_existing_codebuild_tag' not in codebuild_tags

    p = test.load_policy(
        {
            'name': 'cloudwatch-aws-service-log-groups',
            'resource': 'aws.log-group',
            'filters': [
                {
                    'type': 'value',
                    'key': 'logGroupName',
                    'op': 'eq',
                    'value': log_group_name
                }
            ],
            'actions': [
                {
                    'type': 'copy-aws-service-tags',
                    'services': ['codebuild'],
                    'tags': [
                        'copy_tag1',
                        'copy_tag2',
                        'non_existing_codebuild_tag',
                    ]
                }
            ]
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    assert len(resources) == 1

    client = session_factory().client('logs')
    log_group_tags = client.list_tags_log_group(logGroupName=log_group_name)
    assert len(log_group_tags) == 2
    assert log_group_tags['tags']['copy_tag1'] == copy_tag1_value
    assert log_group_tags['tags']['copy_tag2'] == copy_tag2_value
    assert 'non_existing_lambda_tag' not in log_group_tags['tags']


@terraform('copy_multiple_service_tags_to_log_group')
def test_copy_multiple_service_tags_to_log_group(test, copy_multiple_service_tags_to_log_group):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data(
        'test_copy_multiple_service_tags_to_log_group', region=aws_region)

    codebuild_log_group_name = copy_multiple_service_tags_to_log_group[
        'aws_cloudwatch_log_group.codebuild.name']
    codebuild_tags = copy_multiple_service_tags_to_log_group[
        'aws_codebuild_project.this.tags']
    codebuild_copy_tag1_value = codebuild_tags['copy_tag1']
    codebuild_copy_tag2_value = codebuild_tags['copy_tag2']
    assert 'non_existing_codebuild_tag' not in codebuild_tags

    lambda_log_group_name = copy_multiple_service_tags_to_log_group[
        'aws_cloudwatch_log_group.lambda.name']
    lambda_tags = copy_multiple_service_tags_to_log_group[
        'aws_lambda_function.this.tags']
    lambda_copy_tag1_value = lambda_tags['copy_tag1']
    lambda_copy_tag2_value = lambda_tags['copy_tag2']
    assert 'non_existing_lambda_tag' not in lambda_tags

    p = test.load_policy(
        {
            'name': 'cloudwatch-aws-service-log-groups',
            'resource': 'aws.log-group',
            'filters': [
                {
                    'type': 'value',
                    'key': 'logGroupName',
                    'op': 'in',
                    'value': [codebuild_log_group_name, lambda_log_group_name]
                }
            ],
            'actions': [
                {
                    'type': 'copy-aws-service-tags',
                    'services': [
                        'lambda',
                        'codebuild',
                    ],
                    'tags': [
                        'copy_tag1',
                        'copy_tag2',
                        'non_existing_codebuild_tag',
                    ]
                }
            ]
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    assert len(resources) == 2

    client = session_factory().client('logs')

    codebuild_log_group_tags = client.list_tags_log_group(logGroupName=codebuild_log_group_name)
    assert len(codebuild_log_group_tags) == 2
    assert codebuild_log_group_tags['tags']['copy_tag1'] == codebuild_copy_tag1_value
    assert codebuild_log_group_tags['tags']['copy_tag2'] == codebuild_copy_tag2_value
    assert 'non_existing_codebuild_tag' not in codebuild_log_group_tags['tags']

    lambda_log_group_tags = client.list_tags_log_group(logGroupName=lambda_log_group_name)
    assert len(lambda_log_group_tags) == 2
    assert lambda_log_group_tags['tags']['copy_tag1'] == lambda_copy_tag1_value
    assert lambda_log_group_tags['tags']['copy_tag2'] == lambda_copy_tag2_value
    assert 'non_existing_lambda_tag' not in lambda_log_group_tags['tags']


@terraform('copy_lambda_tags_to_log_group_without_related_resource')
def test_copy_lambda_tags_to_log_group_without_related_resource(
    test,
    copy_lambda_tags_to_log_group_without_related_resource
):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data(
        'test_copy_lambda_tags_to_log_group_without_related_resource', region=aws_region)

    log_group_name = copy_lambda_tags_to_log_group_without_related_resource[
        'aws_cloudwatch_log_group.this.name']

    p = test.load_policy(
        {
            'name': 'cloudwatch-aws-service-log-groups',
            'resource': 'aws.log-group',
            'filters': [
                {
                    'type': 'value',
                    'key': 'logGroupName',
                    'op': 'eq',
                    'value': log_group_name
                }
            ],
            'actions': [
                {
                    'type': 'copy-aws-service-tags',
                    'services': ['lambda'],
                    'tags': [
                        'copy_tag1',
                        'copy_tag2',
                        'non_existing_lambda_tag',
                    ]
                }
            ]
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    assert len(resources) == 1

    client = session_factory().client('logs')
    log_group_tags = client.list_tags_log_group(logGroupName=log_group_name)
    assert len(log_group_tags['tags']) == 0


@terraform('copy_codebuild_tags_to_log_group_without_related_resource')
def test_copy_codebuild_tags_to_log_group_without_related_resource(
    test,
    copy_codebuild_tags_to_log_group_without_related_resource
):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data(
        'test_copy_codebuild_tags_to_log_group_without_related_resource', region=aws_region)

    log_group_name = copy_codebuild_tags_to_log_group_without_related_resource[
        'aws_cloudwatch_log_group.this.name']

    p = test.load_policy(
        {
            'name': 'cloudwatch-aws-service-log-groups',
            'resource': 'aws.log-group',
            'filters': [
                {
                    'type': 'value',
                    'key': 'logGroupName',
                    'op': 'eq',
                    'value': log_group_name
                }
            ],
            'actions': [
                {
                    'type': 'copy-aws-service-tags',
                    'services': ['codebuild'],
                    'tags': [
                        'copy_tag1',
                        'copy_tag2',
                        'non_existing_lambda_tag',
                    ]
                }
            ]
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    assert len(resources) == 1

    client = session_factory().client('logs')
    log_group_tags = client.list_tags_log_group(logGroupName=log_group_name)
    assert len(log_group_tags['tags']) == 0
