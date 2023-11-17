from ..azure_common import BaseTest


class KustoTest(BaseTest):

    def test_kusto_resource(self):
        p = self.load_policy(
            {
                "name": "test-kusto-resource",
                "resource": "azure.kusto",
            }
        )
        resources = p.run()

        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]['id'], '/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/'
                                             'resourceGroups/324-rg-red/providers/Microsoft.Kusto/'
                                             'Clusters/kusto324red')

    def test_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-kusto-resource',
                'resource': 'azure.kusto'
            }, validate=True)
            self.assertTrue(p)
