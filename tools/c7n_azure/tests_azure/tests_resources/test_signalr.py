from ..azure_common import BaseTest


class SignalrTest(BaseTest):

    def test_signalr_resource(self):
        p = self.load_policy(
            {
                "name": "test-signalr-resource",
                "resource": "azure.signalr",
            }
        )
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['id'].endswith('/vvnet1'))
