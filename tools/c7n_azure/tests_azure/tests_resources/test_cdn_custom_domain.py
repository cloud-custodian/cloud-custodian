# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class CdnCustomDomainTest(BaseTest):
    def setUp(self):
        super(CdnCustomDomainTest, self).setUp()

    def test_cdn_custom_domain_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-cdn-custom-domain',
                'resource': 'azure.cdn-custom-domain'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cdn-custom-domain.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-cdn-custom-domain',
            'resource': 'azure.cdn-custom-domain',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestcdndomain'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
