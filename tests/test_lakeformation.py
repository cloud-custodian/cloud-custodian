from .common import BaseTest


class DataLakeRegisteredLocation(BaseTest):

    def test_datalake_cross_account_deregister(self):
        factory = self.replay_flight_data('test_datalake_cross_account_deregister')
        p = self.load_policy({
            'name': 'datalake-location-cross-account',
            'resource': 'datalake-location',
            'filters': [{'type': 'cross-account'}],
            'actions': [{'type': 'deregister'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ResourceArn'], 'arn:aws:s3:::unknown-bucket')
        client = factory().client("lakeformation")
        reg_loc = client.list_resources()['ResourceInfoList']
        self.assertEqual(len(reg_loc), 1)
        self.assertNotEqual((r.get('ResourceArn') for r in reg_loc), 'arn:aws:s3:::pratyush-123')
