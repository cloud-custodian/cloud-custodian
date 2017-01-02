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
import logging
import time

from common import BaseTest

from c7n.executor import MainThreadExecutor
from c7n.filters import FilterValidationError
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

    def test_rds_available_engine_upgrades(self):
        session_factory = self.replay_flight_data(
            'test_rds_available_engine_upgrades', zdata=True)
        client = session_factory().client('rds')
        upgrades = rds._get_available_engine_upgrades(client)
        self.assertEqual(upgrades['postgres']['9.3.1'], '9.3.14')
        self.assertEqual(upgrades['sqlserver-ex']['10.50.6000.34.v1'],
                         '10.50.6529.0.v1')
        upgrades = rds._get_available_engine_upgrades(client, major=True)
        self.assertEqual(upgrades['postgres']['9.3.1'], '9.4.9')
        self.assertEqual(upgrades['postgres']['9.4.9'], '9.5.4')
        self.assertEqual(upgrades['sqlserver-ex']['10.50.2789.0.v1'],
                         '12.00.5000.0.v1')

    def test_rds_upgrade_available(self):
        session_factory = self.replay_flight_data(
            'test_rds_minor_upgrade_available')
        p = self.load_policy(
            {'name': 'rds-upgrade-available',
             'resource': 'rds',
             'filters': [
                 {'type': 'upgrade-available', 'major': True},
             ],
             'actions': [{
                 'type': 'mark-for-op',
                 'tag': 'custodian_upgrade',
                 'days': 1,
                 'msg': 'Minor engine upgrade available: {op}@{action_date}',
                 'op': 'upgrade'}],
             }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            {r['EngineVersion']: r.get('c7n-rds-engine-upgrade')
             for r in resources},
            {u'5.6.27': u'5.7.11'})

    def test_rds_minor_upgrade_unavailable(self):
        session_factory = self.replay_flight_data(
            'test_rds_minor_upgrade_unavailable')
        p = self.load_policy(
            {'name': 'rds-upgrade-done',
             'resource': 'rds',
             'filters': [
                 {'type': 'upgrade-available', 'value': False}
             ]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 3)
        self.assertEqual(
            {r['EngineVersion']: r.get('c7n-rds-engine-upgrade')
             for r in resources},
            {u'5.5.41': u'5.5.46', u'5.6.29': None, u'5.7.11': None})

    def test_rds_minor_upgrade_do(self):
        session_factory = self.replay_flight_data(
            'test_rds_minor_upgrade_do')
        p = self.load_policy(
            {'name': 'rds-upgrade-do',
             'resource': 'rds',
             'filters': [
                 {'type': 'marked-for-op', 'tag': 'custodian_upgrade',
                  'op': 'upgrade'}],
             'actions': [{
                 'type': 'upgrade',
                 'immediate': False}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            {r['EngineVersion']: r.get('c7n-rds-engine-upgrade')
             for r in resources},
            {u'5.7.10': None, u'5.6.23': u'5.6.29'})
        self.assertEqual(
            resources[1]['DBInstanceIdentifier'], 'c7n-mysql-test-03')
        self.assertEqual(
            resources[1]['EngineVersion'], '5.6.23')
        self.assertEqual(
            resources[1]['c7n-rds-engine-upgrade'], '5.6.29')

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

    def test_rds_snapshot_access(self):
        factory = self.replay_flight_data('test_rds_snapshot_access')
        p = self.load_policy({
            'name': 'rds-snap-access',
            'resource': 'rds-snapshot',
            'filters': ['cross-account'],
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            {r['DBSnapshotIdentifier']: r['c7n:CrossAccountViolations']
             for r in resources},
            {'tidx-pub': ['all'], 'tidx-rdx': ['619193117841']})

    def test_rds_latest_manual(self):
        # preconditions
        # one db with manual and automatic snapshots
        factory = self.replay_flight_data(
            'test_rds_snapshot_latest')
        p = self.load_policy({
            'name': 'rds-latest-snaps',
            'resource': 'rds-snapshot',
            'filters': [
                {'type': 'latest', 'automatic': False},
            ]}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DBSnapshotIdentifier'],
                         'originb')

    def test_rds_latest(self):
        # preconditions
        # one db with manual and automatic snapshots
        factory = self.replay_flight_data(
            'test_rds_snapshot_latest')
        p = self.load_policy({
            'name': 'rds-latest-snaps',
            'resource': 'rds-snapshot',
            'filters': ['latest']}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DBSnapshotIdentifier'],
                         'rds:originb-2016-12-28-09-15')

    def test_rds_cross_region_copy_lambda(self):
        self.assertRaises(
            FilterValidationError,
            self.load_policy,
            {'name': 'rds-copy-fail',
             'resource': 'rds-snapshot',
             'mode': {
                 'type': 'config-rule'},
             'actions': [{
                 'type': 'region-copy',
                 'target_region': 'us-east-2'}]})

    def test_rds_cross_region_copy_skip_same_region(self):
        self.change_environment(AWS_DEFAULT_REGION='us-east-2')
        factory = self.replay_flight_data('test_rds_snapshot_latest')
        output = self.capture_logging('custodian.actions')
        p = self.load_policy({
            'name': 'rds-copy-skip',
            'resource': 'rds-snapshot',
             'actions': [{
                 'type': 'region-copy',
                 'target_region': 'us-east-2'}]},
            session_factory=factory)
        resources = p.run()
        self.assertFalse([r for r in resources if 'c7n:CopiedSnapshot' in r])
        self.assertIn('Source and destination region are the same',
                      output.getvalue())

    def test_rds_cross_region_copy_many(self):
        # preconditions
        # rds snapshot, encrypted in region with kms, and tags
        # in this scenario we have 9 snapshots in source region,
        # 3 snaps already in target region, 6 to copy, which means
        # we will hit transfer limits.
        factory = self.replay_flight_data(
            'test_rds_snapshot_region_copy_many')

        # no sleep till, beastie boys ;-)
        def brooklyn(delay):
            return

        output = self.capture_logging('c7n.worker', level=logging.DEBUG)
        self.patch(time, 'sleep', brooklyn)
        self.change_environment(AWS_DEFAULT_REGION="us-east-1")
        p = self.load_policy({
            'name': 'rds-snapshot-region-copy',
            'resource': 'rds-snapshot',
            'filters': [
                {'DBInstanceIdentifier': "originb"}],
            'actions': [
                {'type': 'region-copy',
                 'target_region': 'us-east-2',
                 'tags': {'migrated_from': 'us-east-1'},
                 'target_key': 'cb291f53-f3ab-4e64-843e-47b0a7c9cf61'}
                ]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 9)
        self.assertEqual(
            6, len([r for r in resources if 'c7n:CopiedSnapshot' in r]))
        self.assertEqual(output.getvalue().count('retrying'), 2)

    def test_rds_cross_region_copy(self):
        # preconditions
        # rds snapshot, encrypted in region with kms, and tags
        factory = self.replay_flight_data('test_rds_snapshot_region_copy')
        client = factory().client('rds', region_name='us-east-2')
        self.change_environment(AWS_DEFAULT_REGION="us-east-1")
        p = self.load_policy({
            'name': 'rds-snapshot-region-copy',
            'resource': 'rds-snapshot',
            'filters': [
                {'DBSnapshotIdentifier': "rds:originb-2016-12-28-09-15"}],
            'actions': [
                {'type': 'region-copy',
                 'target_region': 'us-east-2',
                 'tags': {'migrated_from': 'us-east-1'},
                 'target_key': 'cb291f53-f3ab-4e64-843e-47b0a7c9cf61'}
                ]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        snapshots = client.describe_db_snapshots(
            DBSnapshotIdentifier=resources[
                0]['c7n:CopiedSnapshot'].rsplit(':', 1)[1])['DBSnapshots']
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]['DBInstanceIdentifier'], 'originb')
        tags = {t['Key']: t['Value'] for t in client.list_tags_for_resource(
            ResourceName=resources[0]['c7n:CopiedSnapshot'])['TagList']}
        self.assertEqual(
            {'migrated_from': 'us-east-1',
             'app': 'mgmt-portal',
             'env': 'staging',
             'workload-type': 'other'},
            tags)

    def test_rds_snapshot_tag_filter(self):
        factory = self.replay_flight_data('test_rds_snapshot_tag_filter')
        client = factory().client('rds')
        p = self.load_policy({
            'name': 'rds-snapshot-tag-filter',
            'resource': 'rds-snapshot',
            'filters': [{'type': 'marked-for-op',
                         'op': 'delete'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(
            resources[0]['DBSnapshotIdentifier'])
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t['Key']: t['Value'] for t in tags['TagList']}
        self.assertTrue('maid_status' in tag_map)
        self.assertTrue('delete@' in tag_map['maid_status'])

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

    def test_rds_snapshot_tag(self):
        factory = self.replay_flight_data('test_rds_snapshot_mark')
        client = factory().client('rds')
        p = self.load_policy({
            'name': 'rds-snapshot-tag',
            'resource': 'rds-snapshot',
            'actions': [{'type': 'tag',
                        'key': 'test-key',
                        'value': 'test-value'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(
            resources[0]['DBSnapshotIdentifier'])
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t['Key']: t['Value'] for t in tags['TagList']}
        self.assertTrue('test-key' in tag_map)
        self.assertTrue('test-value' in tag_map['test-key'])

    def test_rds_snapshot_mark(self):
        factory = self.replay_flight_data('test_rds_snapshot_mark')
        client = factory().client('rds')
        p = self.load_policy({
            'name': 'rds-snapshot-mark',
            'resource': 'rds-snapshot',
            'actions': [{'type': 'mark-for-op',
                        'op': 'delete',
                        'days': 1}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(
            resources[0]['DBSnapshotIdentifier'])
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t['Key']: t['Value'] for t in tags['TagList']}
        self.assertTrue('maid_status' in tag_map)

    def test_rds_snapshot_unmark(self):
        factory = self.replay_flight_data('test_rds_snapshot_unmark')
        client = factory().client('rds')
        p = self.load_policy({
            'name': 'rds-snapshot-unmark',
            'resource': 'rds-snapshot',
            'actions': [{'type': 'unmark'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = p.resource_manager.generate_arn(
            resources[0]['DBSnapshotIdentifier'])
        tags = client.list_tags_for_resource(ResourceName=arn)
        tag_map = {t['Key']: t['Value'] for t in tags['TagList']}
        self.assertFalse('maid_status' in tag_map)


class TestModifyVpcSecurityGroupsAction(BaseTest):
    def test_rds_remove_matched_security_groups(self):
        #
        # Test conditions:
        #    - running 2 Aurora DB clusters in default VPC with 2 instances
        #      each.
        #        - translates to 4 actual instances
        #    - a default security group with id 'sg-7a3fcb13' exists
        #    - security group named PROD-ONLY-Test-Security-Group exists in
        #      VPC and is attached to one set of DB instances
        #        - translates to 2 instances marked non-compliant
        #
        # Results in 4 DB Instances with default Security Group attached

        session_factory = self.replay_flight_data(
            'test_rds_remove_matched_security_groups')
        p = self.load_policy(
            {'name': 'rds-remove-matched-security-groups',
             'resource': 'rds',
             'filters': [
                 {'type': 'security-group',
                  'key': 'GroupName',
                  'value': '(.*PROD-ONLY.*)',
                  'op': 'regex'}],
             'actions': [
                 {'type': 'modify-security-groups',
                  'remove': 'matched',
                  'isolation-group': 'sg-7a3fcb13'}]
             },
            session_factory=session_factory)
        clean_p = self.load_policy(
            {'name': 'rds-verify-remove-matched-security-groups',
             'resource': 'rds',
             'filters': [
                 {'type': 'security-group',
                  'key': 'GroupName',
                  'value': 'default'}]
             },
            session_factory=session_factory)

        resources = p.run()
        clean_resources = clean_p.run()

        # clusters autoscale across AZs, so they get -001, -002, etc appended
        self.assertIn('test-sg-fail', resources[0]['DBInstanceIdentifier'])

        self.assertEqual(len(resources), 2)
        self.assertEqual(len(resources[0]['VpcSecurityGroups']), 1)
        # show that it was indeed a replacement of security groups
        self.assertEqual(len(clean_resources[0]['VpcSecurityGroups']), 1)
        self.assertEqual(len(clean_resources), 4)

    def test_rds_add_security_group(self):
        #
        # Test conditions:
        #   - running 2 Aurora DB clusters in default VPC with 2 instances each
        #        - translates to 4 actual instances
        #    - a default security group with id 'sg-7a3fcb13' exists -
        #      attached to all instances
        #    - security group named PROD-ONLY-Test-Security-Group exists in
        #      VPC and is attached to 2/4 instances
        #        - translates to 2 instances marked to get new group attached
        #
        # Results in 4 instances with default Security Group and
        # PROD-ONLY-Test-Security-Group
        session_factory = self.replay_flight_data(
            'test_rds_add_security_group')
        p = self.load_policy({
            'name': 'add-sg-to-prod-rds',
            'resource': 'rds',
            'filters': [
                {'type': 'security-group',
                 'key': 'GroupName',
                 'value': 'default'},
                {'type': 'value',
                 'key': 'DBInstanceIdentifier',
                 'value': 'test-sg-fail.*', 'op': 'regex'}
            ],
            'actions': [
                {'type': 'modify-security-groups', 'add': 'sg-6360920a'}
            ]
        },
            session_factory=session_factory)

        clean_p = self.load_policy({
            'name': 'validate-add-sg-to-prod-rds',
            'resource': 'rds',
            'filters': [
                {'type': 'security-group', 'key': 'GroupName',
                 'value': 'default'},
                {'type': 'security-group', 'key': 'GroupName',
                 'value': 'PROD-ONLY-Test-Security-Group'}
            ]
        },
            session_factory=session_factory)

        resources = p.run()
        clean_resources = clean_p.run()

        self.assertEqual(len(resources), 2)
        self.assertIn('test-sg-fail', resources[0]['DBInstanceIdentifier'])
        self.assertEqual(len(resources[0]['VpcSecurityGroups']), 1)
        self.assertEqual(len(clean_resources[0]['VpcSecurityGroups']), 2)
        self.assertEqual(len(clean_resources), 4)

