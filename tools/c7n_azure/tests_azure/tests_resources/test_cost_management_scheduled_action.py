# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import PolicyValidationError

from ..azure_common import BaseTest, arm_template, cassette_name


# See ../templates/cost-management-scheduled-action.md for how to provision
# the resource and record cassettes for this test class - it deviates from
# the provision.sh/cleanup.sh convention documented in ../templates/readme.md.
class CostManagementScheduledActionTest(BaseTest):

    def test_schema_validate(self):
        p = self.load_policy({
            'name': 'cost-management-scheduled-action-schema',
            'resource': 'azure.cost-management-scheduled-action',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestscheduledaction'
                }
            ]
        }, validate=True)
        self.assertTrue(p)

    @arm_template('cost-management-scheduled-action.json')
    @cassette_name('common')
    def test_resource(self):
        p = self.load_policy({
            'name': 'cost-management-scheduled-action',
            'resource': 'azure.cost-management-scheduled-action',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestscheduledaction'
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kind'], 'InsightAlert')

    @arm_template('cost-management-scheduled-action.json')
    @cassette_name('healthy-alert')
    def test_healthy_anomaly_alert_not_flagged(self):
        # cctestscheduledaction is Enabled, Daily, with a recipient - it
        # should not be flagged by the benchmark's unhealthy-alert filter.
        p = self.load_policy({
            'name': 'cost-management-scheduled-action-unhealthy',
            'resource': 'azure.cost-management-scheduled-action',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestscheduledaction'
                },
                {'or': [
                    {'type': 'value', 'key': 'properties.status', 'op': 'ne', 'value': 'Enabled'},
                    {'type': 'value', 'key': 'properties.schedule.frequency',
                     'op': 'ne', 'value': 'Daily'},
                    {'type': 'value', 'key': 'properties.notification.to', 'value': 'absent'},
                ]}
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_set_status_schema_validate(self):
        for status in ('Enabled', 'Disabled'):
            p = self.load_policy({
                'name': 'cost-management-scheduled-action-set-status',
                'resource': 'azure.cost-management-scheduled-action',
                'actions': [{'type': 'set-status', 'status': status}]
            }, validate=True)
            self.assertTrue(p)

    def test_set_status_schema_invalid(self):
        for action in ({'type': 'set-status'}, {'type': 'set-status', 'status': 'Expired'}):
            with self.assertRaises(PolicyValidationError):
                self.load_policy({
                    'name': 'cost-management-scheduled-action-set-status',
                    'resource': 'azure.cost-management-scheduled-action',
                    'actions': [action]
                }, validate=True)

    @arm_template('cost-management-scheduled-action.json')
    @cassette_name('enable-disabled-alert')
    def test_z_enable_disabled_alert(self):
        read_policy = self.load_policy({
            'name': 'cost-management-scheduled-action-read-before-enable',
            'resource': 'azure.cost-management-scheduled-action',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestscheduledaction'
                }
            ]
        })

        before = read_policy.run()
        self.assertEqual(len(before), 1)
        self.assertNotEqual(before[0]['properties']['status'], 'Enabled')

        enable_policy = self.load_policy({
            'name': 'cost-management-scheduled-action-enable',
            'resource': 'azure.cost-management-scheduled-action',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestscheduledaction'
                }
            ],
            'actions': [{'type': 'set-status', 'status': 'Enabled'}]
        })
        enable_policy.run()
        self.sleep_in_live_mode(10)

        after = read_policy.run()
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0]['properties']['status'], 'Enabled')

    @arm_template('cost-management-scheduled-action.json')
    @cassette_name('disable-enabled-alert')
    def test_z_disable_enabled_alert(self):
        read_policy = self.load_policy({
            'name': 'cost-management-scheduled-action-read-before-disable',
            'resource': 'azure.cost-management-scheduled-action',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestscheduledaction'
                }
            ]
        })

        before = read_policy.run()
        self.assertEqual(len(before), 1)
        self.assertEqual(before[0]['properties']['status'], 'Enabled')

        disable_policy = self.load_policy({
            'name': 'cost-management-scheduled-action-disable',
            'resource': 'azure.cost-management-scheduled-action',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'value': 'cctestscheduledaction'
                }
            ],
            'actions': [{'type': 'set-status', 'status': 'Disabled'}]
        })
        disable_policy.run()
        self.sleep_in_live_mode(10)

        after = read_policy.run()
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0]['properties']['status'], 'Disabled')
