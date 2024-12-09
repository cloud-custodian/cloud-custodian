# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
from c7n.testing import mock_datetime_now
import c7n.filters.backup
from dateutil import parser


class TestTimestreamDatabase(BaseTest):
    def test_timestream_database_tag(self):
        session_factory = self.replay_flight_data('test_timestream_database_tag')
        p = self.load_policy(
            {
                'name': 'test-timestream-db-tag',
                'resource': 'aws.timestream-database',
                'filters': [
                    {
                        'tag:foo': 'absent'
                    }
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'foo': 'bar'}
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-write')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['Arn'])['Tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]['Key'], 'foo')
        self.assertEqual(tags[0]['Value'], 'bar')

    def test_timestream_database_remove_tag(self):
        session_factory = self.replay_flight_data('test_timestream_database_remove_tag')
        p = self.load_policy(
            {
                'name': 'test-timestream-db-tag',
                'resource': 'aws.timestream-database',
                'filters': [
                    {
                        'tag:foo': 'present'
                    }
                ],
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': ['foo']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-write')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['Arn'])['Tags']
        self.assertEqual(len(tags), 0)

    def test_timestream_database_delete(self):
        session_factory = self.replay_flight_data('test_timestream_database_delete')
        p = self.load_policy(
            {
                'name': 'test-timestream-db-delete',
                'resource': 'aws.timestream-database',
                'actions': [
                    {
                        'type': 'delete',
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-write')
        dbs = client.list_databases()['Databases']
        self.assertEqual(len(dbs), 0)

    def test_timestream_database_delete_force(self):
        session_factory = self.replay_flight_data('test_timestream_database_delete_force')
        p = self.load_policy(
            {
                'name': 'test-timestream-db-delete-force',
                'resource': 'aws.timestream-database',
                'filters': [
                    {"TableCount": 1}
                ],
                'actions': [
                    {
                        'type': 'delete',
                        'force': True
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-write')
        dbs = client.list_databases()['Databases']
        self.assertEqual(len(dbs), 0)


class TestTimestreamTable(BaseTest):
    def test_timestream_table_tag(self):
        session_factory = self.replay_flight_data('test_timestream_table_tag')
        p = self.load_policy(
            {
                'name': 'test-timestream-table-tag',
                'resource': 'aws.timestream-table',
                'filters': [
                    {
                        'tag:foo': 'absent'
                    }
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'foo': 'bar'}
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-write')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['Arn'])['Tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]['Key'], 'foo')
        self.assertEqual(tags[0]['Value'], 'bar')

    def test_timestream_table_remove_tag(self):
        session_factory = self.replay_flight_data('test_timestream_table_remove_tag')
        p = self.load_policy(
            {
                'name': 'test-timestream-table-tag',
                'resource': 'aws.timestream-table',
                'filters': [
                    {
                        'tag:foo': 'present'
                    }
                ],
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': ['foo']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-write')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['Arn'])['Tags']
        self.assertEqual(len(tags), 0)

    def test_timestream_table_delete(self):
        session_factory = self.replay_flight_data('test_timestream_table_delete')
        p = self.load_policy(
            {
                'name': 'test-timestream-table-delete',
                'resource': 'aws.timestream-table',
                'actions': [
                    {
                        'type': 'delete',
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-write')
        tables = client.list_tables()['Tables']
        self.assertEqual(len(tables), 0)

    def test_timestream_consecutive_aws_backup_count_filter(self):
        session_factory = self.replay_flight_data("test_timestream_consecutive_backup_count_filter")
        p = self.load_policy(
            {
                "name": "timestream_consecutive_aws_backup_count_filter",
                "resource": "aws.timestream-table",
                "filters": [
                    {
                        "type": "consecutive-aws-backups",
                        "count": 1,
                        "period": "days",
                        "status": "COMPLETED"
                    }
                ]
            },
            session_factory=session_factory,
        )
        with mock_datetime_now(parser.parse("2024-05-14T22:00:00+00:00"), c7n.filters.backup):
            resources = p.run()
        self.assertEqual(resources[0]['c7n:AwsBackups'][0]['Status'], "COMPLETED")
        self.assertEqual(len(resources), 1)

    def test_timestream_kms_key_filter(self):
        session_factory = self.replay_flight_data('test_timestream_kms_key_filter')
        p = self.load_policy(
            {
                'name': 'timestream_kms_key_filter',
                'resource': 'timestream-database',
                'filters': [
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/test/timestream',
                    },
                ],
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]['c7n:matched-kms-key']), 1)


class TestTimestreamInfluxDB(BaseTest):
    def test_timestream_influx_db_tag(self):
        session_factory = self.replay_flight_data('test_timestream_influx_db_tag')
        p = self.load_policy(
            {
                'name': 'test-timestream-influx-db-tag',
                'resource': 'aws.timestream-influxdb',
                'filters': [
                    {
                        'tag:foo': 'absent'
                    }
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'foo': 'bar'}
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-influxdb')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['arn'])['tags']
        self.assertEqual(len(tags), 1)
        key, value = next(iter(tags.items()))
        self.assertEqual(key, 'foo')
        self.assertEqual(value, 'bar')

    def test_timestream_influx_db_remove_tag(self):
        session_factory = self.replay_flight_data('test_timestream_influx_db_remove_tag')
        p = self.load_policy(
            {
                'name': 'test-timestream-influx-db-remove-tag',
                'resource': 'aws.timestream-influxdb',
                'filters': [
                    {
                        'tag:foo': 'present'
                    }
                ],
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': ['foo']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-influxdb')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['arn'])['tags']
        self.assertEqual(len(tags), 0)

    def test_timestream_influx_db_delete(self):
        session_factory = self.replay_flight_data('test_timestream_influx_db_delete')
        p = self.load_policy(
            {
                'name': 'test-timestream-influx-db-delete',
                'resource': 'aws.timestream-influxdb',
                'actions': [
                    {
                        'type': 'delete',
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('timestream-influxdb')
        db = client.list_db_instances()['items']
        instance = client.get_db_instance(identifier=db[0]['id'])
        self.assertEqual(instance['status'], 'DELETING')

    def test_timestream_influxdb_with_subnet_sg_filter(self):
        factory = self.replay_flight_data("test_timestream_influx_db_subnet_sg")
        p = self.load_policy(
            {
                "name": "timestream_influx_db_subnet_sg",
                "resource": "aws.timestream-influxdb",
                "filters": [
                    {'type': 'subnet',
                     'key': 'tag:Internal',
                     'value': 'False'},
                    {'type': 'security-group',
                     'key': 'tag:c7n-public',
                     'value': 'Policy'}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
