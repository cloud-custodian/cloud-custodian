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
