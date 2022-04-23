# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .azure_common import BaseTest, arm_template, cassette_name


class ParentFilterFunctionalTest(BaseTest):

    def tearDown(self, *args, **kwargs):
        super(ParentFilterFunctionalTest, self).tearDown(*args, **kwargs)

    @arm_template('keyvault.json')
    @cassette_name('keyvault-keys')
    def test_kv_has_keys(self):
        p = self.load_policy({
            'name': 'test-policy',
            'resource': 'azure.keyvault-key',
            'filters': [
                {'type': 'parent',
                 'filter': {
                     'type': 'value',
                     'key': 'name',
                     'op': 'glob',
                     'value': 'cckeyvault1*'
                 }}]
        }, validate=True, cache=True)

        resources = p.run()
        self.assertEqual(len(resources), 2)

    @arm_template('keyvault.json')
    @cassette_name('keyvault-keys')
    def test_kv_has_0_keys(self):
        p = self.load_policy({
            'name': 'test-policy',
            'resource': 'azure.keyvault-key',
            'filters': [
                {'type': 'parent',
                 'filter': {
                     'type': 'value',
                     'key': 'name',
                     'op': 'glob',
                     'value': 'cckeyvault2*'
                 }}]
        }, validate=True, cache=True)

        resources = p.run()
        self.assertEqual(len(resources), 0)
