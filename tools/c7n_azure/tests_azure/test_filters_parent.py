# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_azure.filters import ParentFilter
from c7n_azure.resources.key_vault import KeyVault

from c7n.filters.core import ValueFilter
from .azure_common import BaseTest


class ParentFilterTest(BaseTest):

    def test_schema(self):
        self.assertTrue(self.load_policy({
            'name': 'test-policy',
            'resource': 'azure.keyvault-key',
            'filters': [
                {'type': 'parent',
                 'filter': {
                     'type': 'value',
                     'key': 'name',
                     'op': 'glob',
                     'value': 'cctestkv*'
                 }}]
        }, validate=True))

        self.assertTrue(self.load_policy({
            'name': 'test-policy',
            'resource': 'azure.cosmosdb-collection',
            'filters': [
                {'type': 'parent',
                 'filter': {
                     'type': 'value',
                     'key': 'name',
                     'op': 'glob',
                     'value': 'cctestkv*'
                 }}]
        }, validate=True))

    def test_verify_parent_filter(self):
        p = self.load_policy({
            'name': 'test-policy',
            'resource': 'azure.keyvault-key',
            'filters': [
                {'type': 'parent',
                 'filter': {
                     'type': 'value',
                     'key': 'name',
                     'op': 'glob',
                     'value': 'cctestkv*'
                 }}]})

        self.assertEqual(len(p.resource_manager.filters), 1)

        filter = p.resource_manager.filters[0]
        self.assertTrue(isinstance(filter, ParentFilter))
        self.assertTrue(isinstance(filter.parent_manager, KeyVault))
        self.assertTrue(isinstance(filter.parent_filter, ValueFilter))
