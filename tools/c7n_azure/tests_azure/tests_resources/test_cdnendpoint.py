# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class CdnEndpointTest(BaseTest):
    def setUp(self):
        super(CdnEndpointTest, self).setUp()
        

    def test_endpoint_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-cdnendpoint',
                'resource': 'azure.cdnendpoint'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cdnendpoint.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-cdnendpoint',
            'resource': 'azure.cdnendpoint',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestcdnendpoint'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
