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
from common import BaseTest

from c7n.executor import MainThreadExecutor
from c7n.resources import rds
from c7n import tags


class RDSTest(BaseTest):

    def test_rds_autopatch(self):
        session_factory = self.replay_flight_data('test_rds_auto_patch')
        p = self.load_policy({
            'name': 'rds-tags',
            'resource': 'rds',
            'filters': [
                {'AutoMinorVersionUpgrade': False}],
            'actions': ['auto-patch']},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_tags(self):
        session_factory = self.replay_flight_data('test_rds_tags')
        p = self.load_policy({
            'name': 'rds-tags',
            'resource': 'rds',
            'filters': [
                {'tag:Platform': 'postgres'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_tag_trim(self):
        self.patch(tags.TagTrim, 'max_tag_count', 1)
        session_factory = self.replay_flight_data('test_rds_tag_trim')
        p = self.load_policy({
            'name': 'rds-tags',
            'resource': 'rds',
            'filters': [
                {'tag:Platform': 'postgres'}],
            'actions': [
                {'type': 'tag-trim', 'preserve': ['Name', 'Owner']}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_tag_and_remove(self):
        self.patch(rds.RDS, 'executor_factory', MainThreadExecutor)
        session_factory = self.replay_flight_data('test_rds_tag_and_remove')
        client = session_factory().client('rds')

        p = self.load_policy({
            'name': 'rds-tag',
            'resource': 'rds',
            'filters': [
                {'tag:Platform': 'postgres'}],
            'actions': [
                {'type': 'tag', 'key': 'xyz', 'value': 'hello world'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        arn = p.resource_manager.generate_arn(
            resources[0]['DBInstanceIdentifier'])

        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t['Key']: t['Value'] for t in tags['TagList']}
        self.assertTrue('xyz' in tag_map)

        policy = self.load_policy({
            'name': 'rds-remove-tag',
            'resource': 'rds',
            'filters': [
                {'tag:xyz': 'not-null'}],
            'actions': [
                {'type': 'remove-tag', 'tags': ['xyz']}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t['Key']: t['Value'] for t in tags['TagList']}
        self.assertFalse('xyz' in tag_map)

    def test_rds_mark_and_match(self):
        session_factory = self.replay_flight_data('test_rds_mark_and_match')
        p = self.load_policy({
            'name': 'rds-mark',
            'resource': 'rds',
            'filters': [
                {'tag:Platform': 'postgres'}],
            'actions': [
                {'type': 'mark-for-op', 'tag': 'custodian_next', 'days': 1,
                 'op': 'delete'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        policy = self.load_policy({
            'name': 'rds-mark-filter',
            'resource': 'rds',
            'filters': [
                {'type': 'marked-for-op', 'tag': 'custodian_next',
                 'op': 'delete'}]},
            session_factory=session_factory)
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_rds_default_vpc(self):
        session_factory = self.replay_flight_data('test_rds_default_vpc')
        p = self.load_policy(
            {'name': 'rds-default-filters',
             'resource': 'rds',
             'filters': [
                 {'type': 'default-vpc'}]},
            config={'region': 'us-west-2'},
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_rds_kms_alias(self):
        session_factory = self.replay_flight_data('test_rds_kms_alias')
        p = self.load_policy(
            {'name': 'rds-aws-managed-kms-keys-filters',
             'resource': 'rds',
             'filters': [
                 {'type': 'kms-alias', 'key': 'AliasName',
                  'value': '^(alias/aws/)', 'op': 'regex'}]},
            config={'region': 'us-west-2'},
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_snapshot(self):
        session_factory = self.replay_flight_data('test_rds_snapshot')
        p = self.load_policy(
            {'name': 'rds-snapshot',
             'resource': 'rds',
             'actions': [
                 {'type':'snapshot'}]},
            config={'region': 'us-west-2'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_retention(self):
        session_factory = self.replay_flight_data('test_rds_retention')
        p = self.load_policy(
            {'name': 'rds-snapshot',
             'resource': 'rds',
             'actions': [
                 {'type': 'retention', 'days': 21}]},
            config={'region': 'us-west-2'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 6)

    def test_rds_retention_copy_tags(self):
        session_factory = self.replay_flight_data('test_rds_retention')
        p = self.load_policy(
            {'name': 'rds-snapshot',
             'resource': 'rds',
             'actions': [
                 {'type': 'retention', 'days': 21, 'copy-tags': True}]},
            config={'region': 'us-west-2'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 6)

    def test_rds_delete(self):
        session_factory = self.replay_flight_data('test_rds_delete')
        p = self.load_policy(
            {'name': 'rds-delete',
             'resource': 'rds',
             'filters': [
                 {'tag:Target': 'test'}],
             'actions': [
                 {'type': 'delete',
                  'skip-snapshot': True}]},
            config={'region': 'us-west-2'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_db_instance_eligible_for_backup(self):
        resource = {
            'DBInstanceIdentifier': 'ABC'
        }
        self.assertFalse(rds._db_instance_eligible_for_backup(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'funky'
        }
        self.assertFalse(rds._db_instance_eligible_for_backup(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'available'
        }
        self.assertTrue(rds._db_instance_eligible_for_backup(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'available',
            'DBClusterIdentifier': 'C1'
        }
        self.assertFalse(rds._db_instance_eligible_for_backup(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'available',
            'ReadReplicaSourceDBInstanceIdentifier': 'R1',
            'Engine': 'postgres'
        }
        self.assertFalse(rds._db_instance_eligible_for_backup(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'available',
            'Engine': 'postgres'
        }
        self.assertTrue(rds._db_instance_eligible_for_backup(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'available',
            'Engine': 'mysql',
            'EngineVersion': '5.5.1'
        }
        self.assertTrue(rds._db_instance_eligible_for_backup(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'available',
            'ReadReplicaSourceDBInstanceIdentifier': 'R1',
            'Engine': 'mysql',
            'EngineVersion': '5.5.1'
        }
        self.assertFalse(rds._db_instance_eligible_for_backup(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'available',
            'ReadReplicaSourceDBInstanceIdentifier': 'R1',
            'Engine': 'mysql',
            'EngineVersion': '5.7.1'
        }
        self.assertTrue(rds._db_instance_eligible_for_backup(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'available',
            'ReadReplicaSourceDBInstanceIdentifier': 'R1',
            'Engine': 'mysql',
            'EngineVersion': '6.1.1'
        }
        self.assertTrue(rds._db_instance_eligible_for_backup(resource))

    def test_rds_db_instance_eligible_for_final_snapshot(self):
        resource = {
            'DBInstanceIdentifier': 'ABC'
        }
        self.assertTrue(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'available'
        }
        self.assertTrue(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'creating'
        }
        self.assertFalse(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'failed'
        }
        self.assertFalse(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'incompatible-restore'
        }
        self.assertFalse(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'incompatible-network'
        }
        self.assertFalse(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'available',
            'ReadReplicaSourceDBInstanceIdentifier': 'R1',
            'Engine': 'mysql',
            'EngineVersion': '5.7.1'
        }
        self.assertFalse(rds._db_instance_eligible_for_final_snapshot(resource))

        resource = {
            'DBInstanceIdentifier': 'ABC',
            'DBInstanceStatus': 'available',
            'ReadReplicaSourceDBInstanceIdentifier': '',
            'Engine': 'mysql',
            'EngineVersion': '5.7.1'
        }
        self.assertTrue(rds._db_instance_eligible_for_final_snapshot(resource))


class RDSSnapshotTest(BaseTest):

    def test_rds_snapshot_age_filter(self):
        factory = self.replay_flight_data('test_rds_snapshot_age_filter')
        p = self.load_policy({
            'name': 'rds-snapshot-age-filter',
            'resource': 'rds-snapshot',
            'filters': [{'type': 'age', 'days': 7}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_rds_snapshot_trim(self):
        factory = self.replay_flight_data('test_rds_snapshot_delete')
        p = self.load_policy({
            'name': 'rds-snapshot-trim',
            'resource': 'rds-snapshot',
            'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
