from ..azure_common import BaseTest


class AzureEventGridTopicTest(BaseTest):

    def test_event_grid_topic_schema_validate(self):
        p = self.load_policy({
            'name': 'find-all-event-grid-topics',
            'resource': 'azure.event-grid-topic'
        }, validate=True)
        self.assertTrue(p)

    def test_event_grid_topic_policy_run(self):
        p = self.load_policy({
            'name': 'find-all-event-grid-topics',
            'resource': 'azure.event-grid-topic',
            'filters': [{
                'type': 'value',
                'key': 'properties.privateEndpointConnections[].properties'
                       '.privateLinkServiceConnectionState.status',
                'value': 'Approved',
                'op': 'contains'
            }],
        })
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual('vvegtopic', resources[0]['name'])
