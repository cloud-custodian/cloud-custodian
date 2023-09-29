from ..azure_common import BaseTest


class TestAutomationAccountResource(BaseTest):

    def test_automation_account_resource(self):
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


class TestAutomationAccountFilter(BaseTest):
    def test_automation_account_filter(self):
        p = self.load_policy(
            {
                "name": "test-automation-account-filter",
                "resource": "azure.automation-account",
                "filters": [
                    {
                        "type": "variable-value",
                        "key": "is_encrypted",
                        "op": "eq",
                        "value": False,
                    }
                ],
            }
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'vvtestac')

    def test_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                "name": "test-variable-value-filter",
                "resource": "azure.automation-account",
                "filters": [
                    {
                        "type": "variable-value",
                        "key": "is_encrypted",
                        "op": "eq",
                        "value": False,
                    }
                ],
            }, validate=True)
            self.assertTrue(p)
