# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class BatchTest(BaseTest):
    def setUp(self):
        super(BatchTest, self).setUp()

    def test_batch_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-batch',
                'resource': 'azure.batch'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('batch.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-batch',
            'resource': 'azure.batch',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cctest*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
