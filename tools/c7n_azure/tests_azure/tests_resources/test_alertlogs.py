# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class AlertLogsTest(BaseTest):
    def setUp(self):
        super(AlertLogsTest, self).setUp()

    def test_alert_logs_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-alert-logs',
                'resource': 'azure.alert-logs'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('alert-logs.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-alerts-logs',
            'resource': 'azure.alert-logs',
            'filters': [
                {'type': 'value',
                 'key': 'location',
                 'value': 'Global'},
                {'type': 'value',
                 'key': "properties.condition.allOf[?field=='properties.incidentType'].equals|[0]",
                 'value': 'Incident'},
                {'type': 'value',
                 'key': 'properties.actions.actionGroups',
                 'value': 'not-null'}]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
