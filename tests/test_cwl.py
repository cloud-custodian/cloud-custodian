# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

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
