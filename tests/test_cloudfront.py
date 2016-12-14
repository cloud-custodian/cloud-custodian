

from common import BaseTest

class CloudFront(BaseTest):

    def test_distribution_metric_filter(self):
        factory = self.replay_flight_data('test_distribution_metric_filter')
        p = self.load_policy({
            'name': 'requests-filter',
            'resource': 'distribution',
            'filters': [{
                'type': 'metrics',
                'name': 'Requests',
                'value': 3,
                'op': 'ge'
            }]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(
            resources[0]['DomainName'], 'd1k7b41j4nj6pa.cloudfront.net')
