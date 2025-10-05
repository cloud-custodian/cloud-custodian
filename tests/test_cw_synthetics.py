from .common import BaseTest


class SyntheticsCanaryTest(BaseTest):

    def test_canary_filter_by_tag(self):
        factory = self.replay_flight_data("test_cw_synthetics_tag_filter")
        canary_name = "test_canary_tag"

        p = self.load_policy(
            {
                "name": "filter-canary-by-tag",
                "resource": "cloudwatch-synthetics",
                "filters": [
                    {"type": "value", "key": "tag:MyTagKey", "value": "MyTagValue"}
                ],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Name"], canary_name)
        self.assertEqual(resources[0].get("c7n:MatchedFilters"), ["tag:MyTagKey"])

    def test_delete_canary(self):
        factory = self.replay_flight_data("test_cw_synthetics_delete")
        client = factory().client("synthetics")

        canary_name = "test_canary_delete"

        p = self.load_policy(
            {
                "name": "delete-canary",
                "resource": "cloudwatch-synthetics",
                "filters": [{"Name": canary_name}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)

        canaries = client.describe_canaries()["Canaries"]
        # After deletion, canary should either be gone or in DELETING state
        target_canary = next((c for c in canaries if c["Name"] == canary_name), None)
        if target_canary is not None:
            self.assertEqual(target_canary["Status"]["State"], "DELETING")
        # If target_canary is None, that's also acceptable (fully deleted)

    def test_stop_canary(self):
        factory = self.replay_flight_data("test_cw_synthetics_stop")
        client = factory().client("synthetics")

        canary_name = "test_canary_stop"

        p = self.load_policy(
            {
                "name": "stop-canary",
                "resource": "cloudwatch-synthetics",
                "filters": [{"Name": canary_name}],
                "actions": ["stop"],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        desc = client.get_canary(Name=canary_name)
        self.assertIn(desc["Canary"]["Status"]["State"], ["STOPPED", "STOPPING"])

    def test_start_canary(self):
        factory = self.replay_flight_data("test_cw_synthetics_start")
        client = factory().client("synthetics")

        canary_name = "test_canary_start"

        p = self.load_policy(
            {
                "name": "start-canary",
                "resource": "cloudwatch-synthetics",
                "filters": [{"Name": canary_name}],
                "actions": ["start"],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        desc = client.get_canary(Name=canary_name)
        self.assertIn(desc["Canary"]["Status"]["State"], ["RUNNING", "STARTING"])
