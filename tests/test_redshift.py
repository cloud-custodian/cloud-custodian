from common import BaseTest


class TestRedshift(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('test_redshift_query')
        p = self.load_policy({
            'name': 'redshift-query',
            'resource': 'redshift'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(resources, [])

    def test_parameter(self):
        factory = self.replay_flight_data('test_redshift_parameter')
        p = self.load_policy({
            'name': 'redshift-ssl',
            'resource': 'redshift',
            'filters': [
                {'type': 'param',
                 'key': 'require_ssl',
                 'value': False}]},
            session_factory=factory)
                             
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_delete(self):
        factory = self.replay_flight_data('test_redshift_delete')
        p = self.load_policy({
            'name': 'redshift-ssl',
            'resource': 'redshift',
            'filters': [
                {'ClusterIdentifier': 'c7n-test'}],
            'actions': [
                {'type': 'delete', 'skip-snapshot': True}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        
        
            
