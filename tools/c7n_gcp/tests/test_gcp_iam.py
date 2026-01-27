# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time

from gcp_common import BaseTest, event_data
from googleapiclient.errors import HttpError


class ProjectRoleTest(BaseTest):
    def test_get(self):
        factory = self.replay_flight_data("iam-project-role")

        p = self.load_policy(
            {
                "name": "role-get",
                "resource": "gcp.project-role",
                "mode": {"type": "gcp-audit", "methods": ["google.iam.admin.v1.CreateRole"]},
            },
            session_factory=factory,
        )

        exec_mode = p.get_execution_mode()
        event = event_data("iam-role-create.json")
        roles = exec_mode.run(event, None)

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0]["name"], "projects/cloud-custodian/roles/CustomRole1")

        self.assertEqual(
            p.resource_manager.get_urns(roles),
            ["gcp:iam::cloud-custodian:project-role/CustomRole1"],
        )


class ServiceAccountTest(BaseTest):
    def test_get(self):
        factory = self.replay_flight_data("iam-service-account")
        p = self.load_policy(
            {"name": "sa-get", "resource": "gcp.service-account"}, session_factory=factory
        )
        resource = p.resource_manager.get_resource(
            {
                "project_id": "cloud-custodian",
                # NOTE: flight data doesn't use this email_id.
                "email_id": "devtest@cloud-custodian.iam.gserviceaccount.com",
                # NOTE: unique_id not used at all in the get method.
                "unique_id": "110936229421407410679",
            }
        )
        self.assertEqual(resource["displayName"], "devtest")
        self.assertEqual(
            p.resource_manager.get_urns([resource]),
            [
                # NOTE: compare 'custodian-1291' with email given above.
                "gcp:iam::cloud-custodian:service-account/devtest@custodian-1291.iam.gserviceaccount.com"  # noqa: E501
            ],
        )

    def test_disable(self):
        factory = self.replay_flight_data("iam-service-account-disable")
        p = self.load_policy(
            {"name": "sa-disable", "resource": "gcp.service-account", "actions": ["disable"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query("get", {"name": resources[0]["name"]})
        self.assertTrue(result["disabled"])

    def test_enable(self):
        factory = self.replay_flight_data("iam-service-account-enable")
        p = self.load_policy(
            {"name": "sa-enable", "resource": "gcp.service-account", "actions": ["enable"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        result = client.execute_query("get", {"name": resources[0]["name"]})
        self.assertIsNone(result.get("disabled"))

    def test_delete(self):
        factory = self.replay_flight_data("iam-service-account-delete")
        p = self.load_policy(
            {"name": "sa-delete", "resource": "gcp.service-account", "actions": ["delete"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        try:
            client.execute_query("get", {"name": resources[0]["name"]})
            self.fail("found deleted service account")
        except HttpError as e:
            self.assertTrue("Account deleted" in str(e))

    def test_iam_policy_filter_match(self):
        factory = self.replay_flight_data("iam-service-account-iam-policy")
        p1 = self.load_policy(
            {
                "name": "sa-iam-policy",
                "resource": "gcp.service-account",
                "filters": [
                    {
                        "type": "iam-policy",
                        "doc": {
                            "key": "bindings[?(role=='roles/iam.serviceAccountTest1')].members[]",
                            "value_path": "bindings[?(role=='roles/iam.serviceAccountTest2')].members[]",  # noqa: E501
                            "op": "intersect",
                        },
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p1.run()
        self.assertEqual(len(resources), 1)

    def test_iam_policy_filter_multi_match(self):
        factory = self.replay_flight_data("iam-service-account-iam-policy-multi")
        p1 = self.load_policy(
            {
                "name": "sa-iam-policy",
                "resource": "gcp.service-account",
                "filters": [
                    {
                        "type": "iam-policy",
                        "doc": {
                            "key": "bindings[?(role=='roles/iam.serviceAccountTest1')].members[]",
                            "value_path": "bindings[?(role=='roles/iam.serviceAccountTest2')].members[]",  # noqa: E501
                            "op": "intersect",
                        },
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p1.run()
        self.assertEqual(len(resources), 4)

    def test_iam_policy_filter_no_match(self):
        factory = self.replay_flight_data("iam-service-account-iam-policy")
        p1 = self.load_policy(
            {
                "name": "sa-iam-policy",
                "resource": "gcp.service-account",
                "filters": [
                    {
                        "type": "iam-policy",
                        "doc": {
                            "key": "bindings[?(role=='roles/iam.serviceAccountTest1')].members[]",
                            "value_path": "bindings[?(role=='roles/iam.serviceAccountTest3')].members[]",  # noqa: E501
                            "op": "intersect",
                        },
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p1.run()
        self.assertEqual(len(resources), 0)


class ServiceAccountKeyTest(BaseTest):
    def test_service_account_key_query(self):
        project_id = "cloud-custodian"

        session_factory = self.replay_flight_data("iam-service-account-key-query", project_id)

        policy = self.load_policy(
            {"name": "iam-service-account-key-query", "resource": "gcp.service-account-key"},
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]["keyType"], "SYSTEM_MANAGED")
        self.assertEqual(resources[1]["keyType"], "USER_MANAGED")
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                "gcp:iam::cloud-custodian:service-account-key/test-cutodian-scc@cloud-custodian.iam.gserviceaccount.com/1",  # noqa: E501
                "gcp:iam::cloud-custodian:service-account-key/test-cutodian-scc@cloud-custodian.iam.gserviceaccount.com/2",  # noqa: E501
            ],
        )

    def test_get_service_account_key(self):
        factory = self.replay_flight_data("iam-service-account-key")
        p = self.load_policy(
            {"name": "sa-key-get", "resource": "gcp.service-account-key"}, session_factory=factory
        )
        resource = p.resource_manager.get_resource(
            {
                "resourceName": "//iam.googleapis.com/projects/cloud-custodian/"
                "serviceAccounts/111111111111111/keys/2222"
            }
        )
        self.assertEqual(resource["keyType"], "USER_MANAGED")
        self.assertEqual(
            resource["c7n:service-account"]["email"],
            "test-cutodian-scc@cloud-custodian.iam.gserviceaccount.com",
        )
        self.assertEqual(
            p.resource_manager.get_urns([resource]),
            [
                "gcp:iam::cloud-custodian:service-account-key/test-cutodian-scc@cloud-custodian.iam.gserviceaccount.com/2222",  # noqa: E501
            ],
        )

    def test_delete_service_account_key(self):
        factory = self.replay_flight_data("iam-delete-service-account-key")
        p = self.load_policy(
            {"name": "sa-key-delete", "resource": "gcp.service-account-key", "actions": ["delete"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        try:
            result = client.execute_query("get", {"name": resources[0]["name"]})
            self.fail("found deleted service account key: %s" % result)
        except HttpError as e:
            self.assertTrue("does not exist" in str(e))


class IAMRoleTest(BaseTest):
    def test_iam_role_query(self):
        project_id = "cloud-custodian"

        session_factory = self.replay_flight_data("ami-role-query", project_id)

        policy = self.load_policy(
            {"name": "ami-role-query", "resource": "gcp.iam-role"}, session_factory=session_factory
        )

        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            [
                "gcp:iam:::role/accesscontextmanager.policyAdmin",
                "gcp:iam:::role/spanner.viewer",
            ],
        )

    def test_iam_role_get(self):
        project_id = "cloud-custodian"
        name = "accesscontextmanager.policyAdmin"

        session_factory = self.replay_flight_data("ami-role-query-get", project_id)

        policy = self.load_policy(
            {"name": "ami-role-query-get", "resource": "gcp.iam-role"},
            session_factory=session_factory,
        )

        resource = policy.resource_manager.get_resource(
            {
                "name": name,
            }
        )

        self.assertEqual(resource["name"], "roles/{}".format(name))
        self.assertEqual(
            policy.resource_manager.get_urns([resource]),
            [
                "gcp:iam:::role/accesscontextmanager.policyAdmin",
            ],
        )


class ApiKeyTest(BaseTest):
    def test_api_key_query(self):
        project_id = "cloud-custodian"
        factory = self.replay_flight_data("api-key-list", project_id)
        p = self.load_policy(
            {
                "name": "gcp-api-key-list",
                "resource": "gcp.api-key",
                "filters": [{"name": "projects/cloud-custodian/locations/global/keys/xxxx-xxxx"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_api_key_time_range(self):
        project_id = "cloud-custodian"
        factory = self.replay_flight_data("gcp-apikeys-time-range", project_id)
        p = self.load_policy(
            {
                "name": "gcp-api-key-list",
                "resource": "gcp.api-key",
                "filters": [{
                    "type": "time-range",
                    "value": 30
                }],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["name"],
            "projects/cloud-custodian/locations/global/keys/03b651c2-718a-4702-b5d7-9946987cc4da"
        )
