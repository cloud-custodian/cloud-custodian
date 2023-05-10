# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class CdnCustomDomainTest(BaseTest):
    def setUp(self):
        super(CdnCustomDomainTest, self).setUp()

    def test_customdomain_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-cdncustomdomain',
                'resource': 'azure.cdncustomdomain'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cdncustomdomain.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-cdncustomdomain',
            'resource': 'azure.cdncustomdomain',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestmydomain'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
