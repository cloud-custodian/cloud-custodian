# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class SnapshotTest(BaseTest):

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-disk',
            'resource': 'azure.disk',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'value': 'JamisonsCMKDisk'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
