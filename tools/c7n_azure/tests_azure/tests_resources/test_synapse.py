from ..azure_common import BaseTest


class SynapseTest(BaseTest):

    def test_synapse_resource(self):
        p = self.load_policy(
            {
                "name": "test-synapse-resource",
                "resource": "azure.synapse",
            }
        )
        resources = p.run()

        self.assertEqual(len(resources), 2)
        self.assertTrue(resources[0]['name'].endswith('workspace358-green'))

    def test_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-synapse-resource',
                'resource': 'azure.synapse'
            }, validate=True)
            self.assertTrue(p)
