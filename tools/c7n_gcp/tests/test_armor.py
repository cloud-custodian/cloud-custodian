from gcp_common import BaseTest


class SecurityPolicyTest(BaseTest):
    def test_security_policy_query(self):
        factory = self.replay_flight_data("test_security_policy")
        p = self.load_policy(
            {"name": "security-policy", "resource": "gcp.armor-policy"},
            session_factory=factory,
        )
        resources = p.run()

        self.assertEqual(resources[0]["id"], "2550272938411777319")
        self.assertEqual(len(resources), 1)
        assert p.resource_manager.get_urns(resources) == [
            "gcp:compute::cloud-custodian:securityPolicy/basic-cloud-armor-policy"
        ]

    def test_security_policy_adaptive_protection_enabled(self):
        factory = self.replay_flight_data("test_security_policy")
        p = self.load_policy(
            {
                "name": "security-policy-adaptive-protection-enabled",
                "resource": "gcp.armor-policy",
                "filters": [
                    {
                        "not": [
                            {
                                "type": "value",
                                "key": "adaptiveProtectionConfig.layer7DdosDefenseConfig.enable",
                                "value": "true",
                                "op": "eq",
                            }
                        ]
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["id"], "2550272938411777319")
        self.assertEqual(resources[0]["name"], "basic-cloud-armor-policy")
