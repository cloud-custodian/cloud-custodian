# Copyright 2019 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import azure.keyvault.http_bearer_challenge_cache as kv_cache
from .azure_common import BaseTest, arm_template, cassette_name


class ParentFilterFunctionalTest(BaseTest):

    def tearDown(self, *args, **kwargs):
        super(ParentFilterFunctionalTest, self).tearDown(*args, **kwargs)
        kv_cache._cache = {}

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
