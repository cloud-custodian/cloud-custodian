
from ..azure_common import BaseTest, cassette_name


class NetworkTest(BaseTest):

    # Skip due to Azure Storage RBAC issues when databricks resource is deployed
    def test_vnet_query(self):
        p = self.load_policy({
            'name': 'test-azure-databricks',
            'resource': 'azure.vnet',
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @cassette_name('test_vnet_query')
    def test_query(self):
        p = self.load_policy({
            'name': 'test-azure-subnet',
            'resource': 'azure.subnet',
        })
        resources = p.run()
        self.assertEqual(len(resources), 2)
