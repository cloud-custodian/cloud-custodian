from ..azure_common import BaseTest


class DataLakeAnalyticsTest(BaseTest):

    def setUp(self):
        super(DataLakeAnalyticsTest, self).setUp()

    def test_data_lake_analytics_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-data-lake-analytics',
            'resource': 'azure.datalake-analytics'
        }, validate=True)
        self.assertTrue(p)

    def test_find_active_analytics(self):
        p = self.load_policy({
            'name': 'test-azure-datalake-analytics',
            'resource': 'azure.datalake-analytics',
            'filters': [{
                'type': 'value',
                'key': 'properties.state',
                'value': 'Active'
            }]
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('test2analytics', resources[0]['name'])

    def test_datalake_analytics_diagnostic_settings(self):
        p = self.load_policy({
            'name': 'test-azure-datalake-analytics-diagnostic-settings',
            'resource': 'azure.datalake-analytics',
            'filters': [
                {'type': 'diagnostic-settings',
                 'key': 'logs[].enabled',
                 'op': 'in',
                 'value_type': 'swap',
                 'value': True}],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('test2analytics', resources[0]['name'])
