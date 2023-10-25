from ..azure_common import BaseTest


class MariaDBTest(BaseTest):

    def test_mariadb_server_resource(self):
        p = self.load_policy({
            'name': 'test-mariadb-server',
            'resource': 'azure.mariadb-server'
        })
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'mariadbserver156-red')
