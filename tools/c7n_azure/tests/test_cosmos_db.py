# Copyright 2015-2018 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from azure_common import BaseTest, arm_template


class CosmosDBTest(BaseTest):

    def setUp(self):
        super(CosmosDBTest, self).setUp()

    def test_cosmos_db_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-cosmos-db',
                'resource': 'azure.cosmosdb'
            }, validate=True)
            self.assertTrue(p)

            p = self.load_policy({
                'name': 'test-azure-cosmos-db',
                'resource': 'azure.cosmosdb-database'
            }, validate=True)
            self.assertTrue(p)

            p = self.load_policy({
                'name': 'test-azure-cosmos-db',
                'resource': 'azure.cosmosdb-collection'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('cosmosdb.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestcosmosdb'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('cosmosdb.json')
    def test_find_by_name_database(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-database',
            'filters': [
                {'type': 'value',
                 'key': 'id',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestcdatabase'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('cosmosdb.json')
    def test_find_by_name_collection(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-collection',
            'filters': [
                {'type': 'value',
                 'key': 'id',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cccontainer'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('cosmosdb.json')
    def test_firewall_rules_include(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'firewall-rules',
                 'include': ['3.1.1.1']}],
        })
        resources = p.run()
        print(resources)
        self.assertEqual(1, len(resources))

    @arm_template('cosmosdb.json')
    def test_firewall_rules_include_cidr(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'firewall-rules',
                 'include': ['1.2.2.128/25']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @arm_template('cosmosdb.json')
    def test_firewall_rules_not_equal(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb',
            'filters': [
                {'type': 'firewall-rules',
                 'equal': ['1.0.0.0/1']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @arm_template('cosmosdb.json')
    def test_offer_collection(self):
        p = self.load_policy({
            'name': 'test-azure-cosmosdb',
            'resource': 'azure.cosmosdb-collection',
            'filters': [
                {'type': 'offer',
                 'key': 'content.offerThroughput',
                 'op': 'gt',
                 'value': 100}],
        })
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('Hash', resources[0]['partitionKey']['kind'])
