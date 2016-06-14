from common import BaseTest

from c7n.executor import MainThreadExecutor
from c7n.resources import rds


class RDSTest(BaseTest):

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

        arn = "arn:aws:rds:%s:%s:db:%s" % (
            p.resource_manager.config.region, p.resource_manager.account_id,
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
                {'type': 'mark-for-op', 'tag': 'custodian_next', 'days': -1,
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
        self.assertEqual(len(resources), 1)

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


class RDSSnapshotTrimTest(BaseTest):

    def test_rds_snapshot_trim(self):
        factory = self.replay_flight_data('test_rds_snapshot_delete')
        p = self.load_policy({
            'name': 'rds-snapshot-trim',
            'resource': 'rds-snapshot',
            'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
