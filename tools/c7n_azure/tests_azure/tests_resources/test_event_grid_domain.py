from ..azure_common import BaseTest


class AzureEventGridDomainTest(BaseTest):

    def test_event_grid_domain_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'find-all-event-grid-domains',
                'resource': 'azure.event-grid-domain'
            }, validate=True)
            self.assertTrue(p)

    def test_event_grid_domain_policy_run(self):
        p = self.load_policy({
            'name': 'find-all-event-grid-domains',
            'resource': 'azure.event-grid-domain',
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
        self.assertEqual('testegvv', resources[0]['name'])
