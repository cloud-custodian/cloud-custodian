from common import BaseTest
from c7n.utils import local_session


class CloudTrail(BaseTest):

    def test_create(self):
        p_trails = ['nosetest']
        factory = self.replay_flight_data('test_cloudtrail_create')
        p = self.load_policy(
            {
                'name': 'trail-test',
                'resource': 'cloudtrail',
                'actions': [
                    {
                        'type': 'enable',
                        'trails': p_trails,
                    },
                ],
            },
            session_factory=factory,
        )
        p.run()
        client = local_session(factory).client('cloudtrail')
        resp = client.describe_trails(trailNameList=p_trails)
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
                        'trails': ['nosetest'],
                    },
                ],
            },
            session_factory=factory,
        )
        trails = p.run()
        client = local_session(factory).client('cloudtrail')
        arn = trails[0]['TrailARN']
        status = client.get_trail_status(Name=arn)
        self.assertTrue(status['IsLogging'])
