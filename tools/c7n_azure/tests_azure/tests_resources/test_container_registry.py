# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class ContainerRegistryTest(BaseTest):
    def setUp(self):
        super(ContainerRegistryTest, self).setUp()

    def test_container_registry_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-container-registry',
                'resource': 'azure.containerregistry'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('container_registry.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-containerregistry',
            'resource': 'azure.containerregistry',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cctestcontainerregistry*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
