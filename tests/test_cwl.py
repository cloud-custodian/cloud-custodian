
from common import BaseTest


class LogGroupTest(BaseTest):

    def xtest_last_write(self):
        self.record_flight_data('test_log_group_last_write')
        
    def test_retention(self):
        log_group = 'c7n-test-a'
        factory = self.replay_flight_data('test_log_group_retention')
        client = factory().client('logs')
        client.create_log_group(logGroupName=log_group)
        self.addCleanup(client.delete_log_group, logGroupName=log_group)
        p = self.load_policy(
            {'name': 'set-retention',
             'resource': 'log-group',
             'filters': [{
                 'logGroupName': log_group}],
             'actions': [
                 {'type': 'retention', 'days': 14}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            client.describe_log_groups(
                logGroupNamePrefix=log_group)['logGroups'][0]['retentionInDays'],
            14)
    
    def test_delete(self):
        log_group = 'c7n-test-b'
        factory = self.replay_flight_data('test_log_group_delete')
        client = factory().client('logs')
        client.create_log_group(logGroupName=log_group)
        
        p = self.load_policy(
            {'name': 'delete-log-group',
             'resource': 'log-group',
             'filters': [{
                 'logGroupName': log_group}],
             'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['logGroupName'], log_group)
        self.assertEqual(
            client.describe_log_groups(
                logGroupNamePrefix=log_group)['logGroups'], [])
             
