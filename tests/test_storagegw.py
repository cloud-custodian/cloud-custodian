from .common import BaseTest


class TestStorageGateway(BaseTest):

    def test_storage_gateway_tag(self):
        session_factory = self.record_flight_data("test_storage_gateway_tag")
        client = session_factory().client("storagegateway")
        p = self.load_policy(
            {
                "name": "storage-gw-tag",
                "resource": "storage-gateway",
                "filters": [{"GatewayTimezone": "GMT-8:00"}],
                "actions": [
                    {
                        "type": "tag",
                        "key": "TestTag",
                        "value": "c7n"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(ResourceARN=resources[0]["GatewayARN"])['Tags']
        self.assertEqual(tags[0]['Key'], 'TestTag')
        self.assertEqual(tags[0]['Value'], 'c7n')

        p = self.load_policy(
            {
                "name": "storage-gw-untag",
                "resource": "storage-gateway",
                "filters": [{"tag:TestTag": "c7n"}],
                "actions": [{"type": "remove-tag", "tags": ["TestTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(ResourceARN=resources[0]["GatewayARN"])['Tags']
        self.assertEqual(len(tags), 0)
