from .common import BaseTest


class LambdaTest(BaseTest):

    def test_sg_filter(self):
        factory = self.replay_flight_data('test_aws_lambda_sg')

        p = self.load_policy({
            'name': 'sg-lambda',
            'resource': 'lambda',
            'filters': [
                {'FunctionName': 'mys3'},
                {'type': 'security-group',
                 'key': 'GroupName',
                 'value': 'default'}
                ]}, session_factory=factory)
        resources = p.run()
        self.assertEqual(resources[0]['FunctionName'], 'mys3')
        self.assertEqual(
            resources[0]['c7n.matched-security-groups'],
            ['sg-f9cc4d9f'])
