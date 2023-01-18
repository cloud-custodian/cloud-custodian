import datetime
from dateutil.parser import parse as date_parse

from ..azure_common import BaseTest
from c7n.testing import mock_datetime_now


class ActivityLogTest(BaseTest):

    def test_activity_log_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-activity-log',
                'resource': 'azure.activity-log'
            }, validate=True)
            self.assertTrue(p)

    def test_find_by_operation_name(self):
        operation_name = 'Microsoft.Resources/subscriptions/resourcegroups/delete'
        p = self.load_policy({
            'name': 'test-azure-activity-log',
            'resource': 'azure.activity-log',
            'filters': [
                {'type': 'value',
                 'key': 'operationName.value',
                 'op': 'eq',
                 'value': operation_name}]
        })
        with mock_datetime_now(date_parse('2021/08/23 00:00'), datetime):
            resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual(operation_name, resources[0]['operationName']['value'])
