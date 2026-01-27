# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class SpringAppsTest(BaseTest):
    def test_azure_springapps_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-springapps-schema-validate',
            'resource': 'azure.spring-app'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-azure-springapps',
            'resource': 'azure.spring-app',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'value': 'test-spring-app'}]
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
