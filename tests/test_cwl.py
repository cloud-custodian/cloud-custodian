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
from .common import BaseTest, functional
from unittest.mock import MagicMock


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
        self.assertEqual(resources[0]['creationTime'], 1548368507.441)

    def test_last_write(self):
        factory = self.replay_flight_data("test_log_group_last_write")
        p = self.load_policy(
            {
                "name": "set-retention",
                "resource": "log-group",
                "filters": [
                    {"logGroupName": "/aws/lambda/ec2-instance-type"},
                    {"type": "last-write", "days": 0.1},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["logGroupName"], "/aws/lambda/ec2-instance-type")

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
