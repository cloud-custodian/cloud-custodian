
from common import BaseTest


class ElasticFileSystem(BaseTest):

    def test_resource_manager(self):
        factory = self.replay_flight_data('test_efs_query')
        p = self.load_policy({
            'name': 'efs-query',
            'resource': 'efs',
            'filters': [{'Name': 'MyDocs'}],
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['NumberOfMountTargets'], 4)

    def test_delete(self):
        factory = self.replay_flight_data('test_efs_delete')
        p = self.load_policy({
            'name': 'efs-query',
            'resource': 'efs',
            'filters': [{'Name': 'MyDocs'}],
            'actions': ['delete']
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'MyDocs')
        client = factory().client('efs')
        state = client.describe_file_systems().get('FileSystems', [])
        self.assertEqual(state, [])

