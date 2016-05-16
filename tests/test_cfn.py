
from common import BaseTest


class TestCFN(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data('test_cfn_query')
        p = self.load_policy({
            'name': 'cfn-query',
            'resource': 'cfn'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(resources, [])
        
        
