import time

from c7n_gcp.resources.armor import SecurityPolicy
from gcp_common import BaseTest
from pytest_terraform import terraform


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


@terraform("armor_policy_set_labels")
def test_security_policy_set_labels(test, armor_policy_set_labels):
    project_id = armor_policy_set_labels["google_compute_security_policy.default.project"]
    policy_name = armor_policy_set_labels["google_compute_security_policy.default.name"]

    factory = test.replay_flight_data("armor-policy-set-label", project_id=project_id)
    policy = test.load_policy(
        {
            "name": "armor-policy-set-label",
            "resource": "gcp.armor-policy",
            "filters": [{"name": policy_name}],
            "actions": [{"type": "set-labels", "labels": {"env": "not-the-default"}}],
        },
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1
    assert resources[0]["labels"]["env"] == "default"

    client = policy.resource_manager.get_client()
    result = client.execute_query(
        "get",
        {"project": project_id, "securityPolicy": policy_name},
    )
    assert result["labels"]["env"] == "not-the-default"


@terraform("armor_policy_refresh")
def test_security_policy_refresh(test, armor_policy_refresh):
    # Policy is created by terraform.
    project_id = armor_policy_refresh["google_compute_security_policy.default.project"]
    policy_name = armor_policy_refresh["google_compute_security_policy.default.name"]
    self_link = armor_policy_refresh["google_compute_security_policy.default.self_link"]
    original_labels = armor_policy_refresh["google_compute_security_policy.default.labels"]
    original_label_fingerprint = armor_policy_refresh[
        "google_compute_security_policy.default.label_fingerprint"
    ]

    # Update the policy's labels manually.
    factory = test.replay_flight_data("armor-policy-refresh", project_id=project_id)
    client = factory().client("compute", "v1", "securityPolicies")
    updated_labels = dict(original_labels, env="refreshed")
    client.execute_command(
        "setLabels",
        {
            "project": project_id,
            "resource": policy_name,
            "body": {
                "labels": updated_labels,
                "labelFingerprint": original_label_fingerprint,
            },
        },
    )
    if test.recording:
        time.sleep(1)

    # Check that the refresh method returns the updated labels and new label fingerprint
    resource = SecurityPolicy.resource_type.refresh(client, {"selfLink": self_link})
    assert resource["labels"] == updated_labels
    assert resource["labelFingerprint"] != original_label_fingerprint
