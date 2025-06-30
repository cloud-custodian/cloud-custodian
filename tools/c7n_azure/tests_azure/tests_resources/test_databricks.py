# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest

from ..azure_common import BaseTest, arm_template


class DatabricksTest(BaseTest):
    def test_databricks_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-databricks',
                'resource': 'azure.databricks'
            }, validate=True)
            self.assertTrue(p)

    # Skip due to Azure Storage RBAC issues when databricks resource is deployed
    @arm_template('databricks.json')
    @pytest.mark.skiplive
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-databricks',
            'resource': 'azure.databricks',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'custodiandatabricks'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class DatabricksVnetFilterTest(BaseTest):
    def test_databricks_vnet_filter_schema_prefix(self):
        p = self.load_policy({
            'name': 'test-azure-databricks-vnet-filter',
            'resource': 'azure.databricks',
            'filters': [
                {'type': 'vnet',
                 'key': 'properties.addressSpace.addressPrefixes',
                 'op': 'contains',
                 'value': '10.0.0.0/16'}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:Vnet']['properties']['addressSpace']['addressPrefixes'], ['10.0.0.0/16'])


class DatabricksSubnetsFilterTest(BaseTest):
    def test_databricks_vnet_filter_schema_prefix(self):
        p = self.load_policy({
            'name': 'test-azure-databricks-vnet-filter',
            'resource': 'azure.databricks',
            'filters': [{
                'type': 'subnets',
                'attrs': [{
                     'type': 'value',
                     'key': 'properties.addressPrefix',
                     'value': '10.0.2.0/24'
                 }]
            }]
        }, validate=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:Subnets'][1]['properties']['addressPrefix'], '10.0.2.0/24')
