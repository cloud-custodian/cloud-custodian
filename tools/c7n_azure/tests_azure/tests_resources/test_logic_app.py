# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class LogicAppTest(BaseTest):
    def test_azure_logic_app_workflow_schema_validate(self):
        p = self.load_policy({
            'name': 'test-azure-logic-app-workflow',
            'resource': 'azure.logic-app-workflow'
        }, validate=True)
        self.assertTrue(p)

    def test_find_workflow_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-logic-app-workflow',
            'resource': 'azure.logic-app-workflow',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cclogicapp*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
