# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class NetworkWatcherTest(BaseTest):

    def test_network_watcher_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-network-watcher',
                'resource': 'azure.networkwatcher'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('network_watcher.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-network-watcher',
            'resource': 'azure.networkwatcher',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'networkWatcher'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
