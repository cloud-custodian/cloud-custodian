# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class ResourceGroupTest(BaseTest):
    def setUp(self):
        super(ResourceGroupTest, self).setUp()

    def test_resource_group_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-resource-group',
                'resource': 'azure.resourcegroup',
                'filters': [
                    {'type': 'empty-group'}
                ],
                'actions': [
                    {'type': 'delete'}
                ]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('emptyrg.json')
    def test_empty_group(self):
        p = self.load_policy({
            'name': 'test-azure-resource-group',
            'resource': 'azure.resourcegroup',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'test_emptyrg'},
                {'type': 'empty-group'}]})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'test_emptyrg')
