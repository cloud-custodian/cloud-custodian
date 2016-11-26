from common import BaseTest


class SimpleDBTest(BaseTest):

    def test_simpledb(self):
        session_factory = self.replay_flight_data('test_simpledb_query')
        p = self.load_policy({
            'name': 'sdbtest',
            'resource': 'simpledb'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DomainName'], 'devtest')
