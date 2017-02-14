from common import BaseTest
from c7n.utils import local_session


TRAIL = 'nosetest'


class CloudTrail(BaseTest):

    def test_create(self):
        factory = self.replay_flight_data('test_cloudtrail_create')
        p = self.load_policy(
            {
                'name': 'trail-test',
                'resource': 'cloudtrail',
                'actions': [
                    {
                        'type': 'enable',
                        'trail': TRAIL,
                        'bucket': '%s-bucket' % TRAIL,
                    },
                ],
            },
            session_factory=factory,
        )
        p.run()
        client = local_session(factory).client('cloudtrail')
        resp = client.describe_trails(trailNameList=[TRAIL])
        trails = resp['trailList']
        arn = trails[0]['TrailARN']
        status = client.get_trail_status(Name=arn)
        self.assertTrue(status['IsLogging'])

    def test_enable(self):
        factory = self.replay_flight_data('test_cloudtrail_enable')
        p = self.load_policy(
            {
                'name': 'trail-test',
                'resource': 'cloudtrail',
                'actions': [
                    {
                        'type': 'enable',
                        'trail': TRAIL,
                        'bucket': '%s-bucket' % TRAIL,
                        'multi-region': False,
                        'global-events': False,
                        'notify': 'test',
                        'file-digest': True,
                        'kms': True,
                        'kms_key': 'arn:aws:kms:us-east-1:1234:key/fake',
                    },
                ],
            },
            session_factory=factory,
        )
        p.run()
        client = local_session(factory).client('cloudtrail')
        resp = client.describe_trails(trailNameList=[TRAIL])
        trails = resp['trailList']
        test_trail = trails[0]
        self.assertFalse(test_trail['IsMultiRegionTrail'])
        self.assertFalse(test_trail['IncludeGlobalServiceEvents'])
        self.assertTrue(test_trail['LogFileValidationEnabled'])
        self.assertEqual(test_trail['SnsTopicName'], 'test')
        arn = test_trail['TrailARN']
        status = client.get_trail_status(Name=arn)
        self.assertTrue(status['IsLogging'])
