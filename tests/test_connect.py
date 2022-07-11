from .common import BaseTest


class ConnectTest(BaseTest):

    def test_connect_query(self):
        session_factory = self.replay_flight_data("test_connect_query")
        p = self.load_policy(
            {
                "name": "connect-query-test",
                "resource": "connect-instance"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connect_instance_attribute(self):
        session_factory = self.replay_flight_data("test_connect_instance_attribute")
        p = self.load_policy(
            {
                "name": "connect-instance-attribute-test",
                "resource": "connect-instance",
                "filters": [{
                    'type': 'instance-attribute',
                    'key': 'Attribute.Value',
                    'value': 'true',
                    'attribute_type': 'CONTACT_LENS'
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
