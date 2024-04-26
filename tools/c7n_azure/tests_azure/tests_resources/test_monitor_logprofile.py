# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class MonitorLogprofileTest(BaseTest):
    def test_azure_monitor_logprofile_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-monitor-log-profile-schema-validate',
            'resource': 'azure.monitor-log-profile'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-azure-monitor-log-profile',
            'resource': 'azure.monitor-log-profile',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'value': 'testlogprofile'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_find_storage(self):
        p = self.load_policy({
            'name': 'test-azure-azure-monitor-log-profile-storage',
            'resource': 'azure.monitor-log-profile',
            'filters': [
                {'type': 'monitor-storage',
                 'key': 'properties.encryption.keySource',
                 'op': 'eq',
                 "value_type": "normalize",
                 'value': 'microsoft.keyvault'
                 }],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
