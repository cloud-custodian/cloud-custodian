
from common import BaseTest


class ElasticSearch(BaseTest):

    def test_resource_manager(self):
        factory = self.replay_flight_data('test_elasticsearch_query')
        p = self.load_policy({
            'name': 'es-query',
            'resource': 'elasticsearch',
            'filters': [{'DomainName': 'indexme'}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DomainName'], 'indexme')

    def test_delete_search(self):
        factory = self.replay_flight_data('test_elasticsearch_delete')
        p = self.load_policy({
            'name': 'es-query',
            'resource': 'elasticsearch',
            'filters': [{'DomainName': 'indexme'}],
            'actions': ['delete']
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['DomainName'], 'indexme')

        client = factory().client('es')

        state = client.describe_elasticsearch_domain(
            DomainName='indexme')['DomainStatus']
        self.assertEqual(state['Deleted'], True)

