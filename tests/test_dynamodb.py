from common import BaseTest


class DynamodbTest(BaseTest):

    def test_resources(self):
        session_factory = self.replay_flight_data('test_dynamodb_table')
        p = self.load_policy(
            {'name': 'tables',
             'resource': 'dynamodb-table'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['TableName'], 'rolltop')
        self.assertEqual(resources[0]['TableStatus'], 'ACTIVE')

    def test_invoke_action(self):
        session_factory = self.replay_flight_data(
            'test_dynamodb_invoke_action')
        p = self.load_policy(
            {'name': 'tables',
             'resource': 'dynamodb-table',
             'actions': [
                 {'type': 'invoke-lambda',
                  'function': 'process_resources'}
             ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
