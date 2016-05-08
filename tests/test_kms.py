from common import BaseTest


class KMSTest(BaseTest):

    def test_kms_grant(self):
        self.replay_flight_data('test_kms_grants', zdata=True)
        p = self.load_policy(
            {'name': 'kms-grant-count',
             'resource': 'kms',
             'filters': [
                 {'type': 'grant-count'}]})

        resources = p.run()
        self.assertEqual(len(resources), 0)

        

        
        
