from ..azure_common import BaseTest


class ActivityLogAlertTest(BaseTest):

    def test_activity_log_alert_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-activity-log-alert',
                'resource': 'azure.activity-log-alert'
            }, validate=True)
            self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-activity-log-alert',
            'resource': 'azure.activity-log-alert',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'value': 'rule1'}]
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('rule1', resources[0]['name'])

    def test_by_custom_filter(self):
        p = self.load_policy({
            'name': 'test-azure-activity-log-alert-by-filter',
            'resource': 'azure.activity-log-alert',
            'filters': [
                {
                    'type': 'value',
                    'key': 'location',
                    'value': 'Global'
                }, {
                    'type': 'value',
                    'key': 'properties.enabled',
                    'value': True
                }, {
                    'type': 'value',
                    'key': 'properties.condition.allOf[1].equals',
                    'value': 'LiveArena.Broadcast/services/listSecrets/action'
                }
            ]
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('rule2', resources[0]['name'])
