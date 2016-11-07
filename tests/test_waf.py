from common import BaseTest


class WAFTest(BaseTest):

    def test_waf_query(self):
        session_factory = self.replay_flight_data('test_waf_query')
        p = self.load_policy({
            'name': 'waftest',
            'resource': 'waf'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['WebACLId'], '1ebe0b46-0fd2-4e07-a74c-27bf25adc0bf')

        
        
