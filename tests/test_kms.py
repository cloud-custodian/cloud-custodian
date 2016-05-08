from common import BaseTest


class KMSTest(BaseTest):

    def test_kms_grant(self):
        session_factory = self.replay_flight_data('test_kms_grants')
        p = self.load_policy(
            {'name': 'kms-grant-count',
             'resource': 'kms',
             'filters': [
                 {'type': 'grant-count'}]},
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 0)

        

        
        
