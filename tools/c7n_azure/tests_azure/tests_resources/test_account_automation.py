from ..azure_common import BaseTest


class AutomationAccountTest(BaseTest):

    def test_query(self):
        p = self.load_policy(
            {
                "name": "test-automation-account-resource",
                "resource": "azure.automation-account",
                "filters": [
                    {
                        "type": "value",
                        "key": "location",
                        "value": "eastus",
                    }
                ],
            }
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'VVtest')

    def test_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-automation-account-resource',
                'resource': 'azure.automation-account'
            }, validate=True)
            self.assertTrue(p)


class AutomationAccountVariableFilterTest(BaseTest):
    def test_query(self):
        p = self.load_policy(
            {
                "name": "test-automation-account-filter",
                "resource": "azure.automation-account",
                "filters": [
                    {
                        "type": "variable",
                        "attrs": [
                            {
                                "type": "value",
                                "key": "properties.isEncrypted",
                                "value": False
                            }
                        ]
                    }
                ],
            }
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'vvtestac')
        self.assertEqual(len(resources[0]['c7n:Variables']), 1)

    def test_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                "name": "test-variable-filter",
                "resource": "azure.automation-account",
                "filters": [
                    {
                        "type": "variable",
                        "attrs": [
                            {
                                "type": "value",
                                "key": "properties.isEncrypted",
                                "value": False
                            }
                        ]
                    }
                ],
            }, validate=True)
            self.assertTrue(p)
