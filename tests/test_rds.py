from common import BaseTest


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
