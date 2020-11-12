# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class SearchTest(BaseTest):

    @arm_template('search.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-search',
            'resource': 'azure.search',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestsearch*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['properties']['replicaCount'], 1)
