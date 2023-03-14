# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class TrafficManagerTest(BaseTest):
    def test_azure_disk_schema_validate(self):
        p = self.load_policy({
            'name': 'test-traffic-manager-profile',
            'resource': 'azure.traffic-manager-profile'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-traffic-manager-profile',
            'resource': 'azure.traffic-manager-profile',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctraffic*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
