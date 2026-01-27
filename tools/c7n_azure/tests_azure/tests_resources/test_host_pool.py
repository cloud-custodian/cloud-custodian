# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class HostPoolTest(BaseTest):
    def test_host_pool_schema_validate(self):
        p = self.load_policy({
            'name': 'test-host-pool-schema',
            'resource': 'azure.host-pool'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-host-pool-by-name',
            'resource': 'azure.host-pool',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctesthostpools*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
