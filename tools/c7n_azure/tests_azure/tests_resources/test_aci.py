# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template, cassette_name


class ContainerGroupTest(BaseTest):
    def test_containergroup_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test',
                'resource': 'azure.container-group'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('aci.json')
    @cassette_name('list')
    def test_find_container_by_name(self):
        p = self.load_policy({
            'name': 'test',
            'resource': 'azure.container-group',
            'filters': [
                {'type': 'value',
                 'key': 'properties.containers[].name',
                 'op': 'in',
                 'value_type': 'swap',
                 'value': 'cctest-container'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
