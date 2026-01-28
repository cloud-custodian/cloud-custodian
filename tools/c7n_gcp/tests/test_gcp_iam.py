# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import time
from unittest import mock

import pytest
from pytest_terraform import terraform

from gcp_common import BaseTest, event_data
from googleapiclient.errors import HttpError

from c7n.utils import local_session
from c7n_gcp.resources.iam import RoleDeleteAction


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


class RoleDeleteActionTest(BaseTest):
    # Unittests for RoleDeleteAction
    def setUp(self):
        super().setUp()
        self.rda = RoleDeleteAction()
        self.full_org_role = "organizations/111111111111/roles/customRole1"
        self.full_proj_role = "projects/123123123123/roles/customRole2"

    def test_is_organizational_role_success(self):
        self.assertTrue(self.rda.is_organizational_role(self.full_org_role))

    def test_is_organizational_role_fail(self):
        self.assertFalse(self.rda.is_organizational_role(self.full_proj_role))

    def test_get_organizational_role_name_success(self):
        self.assertEqual(
            self.rda.get_organizational_role_name(self.full_org_role),
            "customRole1",
        )

    def test_get_organizational_role_name_fail(self):
        self.assertEqual(
            self.rda.get_organizational_role_name(self.full_proj_role),
            None,
        )

    def test_is_project_role_success(self):
        self.assertTrue(self.rda.is_project_role(self.full_proj_role))

    def test_is_project_role_fail(self):
        self.assertFalse(self.rda.is_project_role(self.full_org_role))

    def test_get_project_role_name_success(self):
        self.assertEqual(
            self.rda.get_project_role_name(self.full_proj_role),
            "customRole2",
        )

    def test_get_project_role_name_fail(self):
        self.assertEqual(
            self.rda.get_project_role_name(self.full_org_role),
            None,
        )

    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.handle_resource_error",
    )
    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.invoke_api",
    )
    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.get_resource_params",
        return_value={
            "name": "organizations/111111111111/roles/customRole1",
        },
    )
    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.get_operation_name",
        return_value="iam.organizations.roles.delete",
    )
    def test_handle_role_delete_org(
        self,
        mock_get_op,
        mock_get_params,
        mock_invoke,
        mock_error,
    ):
        override_client = mock.MagicMock()
        model = mock.MagicMock()
        resource = {
            "name": "organizations/111111111111/roles/customRole1",
            "title": "Custom Role",
            "description": "Custom role for testing",
            "includedPermissions": [],
            "stage": "GA",
            "etag": "BwYGhFMnKpQ=",
            "deleted": False,
        }

        # Nothing should get raised, & no return value.
        self.rda.handle_role_delete(
            override_client,
            model,
            resource,
            "customRole1",
        )

        # And verify the mocks for correct-looking calls.
        mock_get_op.assert_called_once_with(
            model,
            resource,
        )
        mock_get_params.assert_called_once_with(
            model,
            resource,
        )
        mock_invoke.assert_called_once_with(
            override_client,
            "iam.organizations.roles.delete",
            {
                "name": "organizations/111111111111/roles/customRole1",
            },
        )
        mock_error.assert_not_called()

    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.handle_resource_error",
    )
    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.invoke_api",
    )
    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.get_resource_params",
        return_value={
            "name": "projects/123123123123/roles/customRole2",
        },
    )
    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.get_operation_name",
        return_value="iam.projects.roles.delete",
    )
    def test_handle_role_delete_proj(
        self,
        mock_get_op,
        mock_get_params,
        mock_invoke,
        mock_error,
    ):
        override_client = mock.MagicMock()
        model = mock.MagicMock()
        resource = {
            "name": "projects/123123123123/roles/customRole2",
            "title": "Custom Role",
            "description": "Custom role for testing",
            "includedPermissions": [],
            "stage": "GA",
            "etag": "AwYGhFMnKpQ=",
            "deleted": False,
        }

        # Nothing should get raised, & no return value.
        self.rda.handle_role_delete(
            override_client,
            model,
            resource,
            "customRole2",
        )

        # And verify the mocks for correct-looking calls.
        mock_get_op.assert_called_once_with(
            model,
            resource,
        )
        mock_get_params.assert_called_once_with(
            model,
            resource,
        )
        mock_invoke.assert_called_once_with(
            override_client,
            "iam.projects.roles.delete",
            {
                "name": "projects/123123123123/roles/customRole2",
            },
        )
        mock_error.assert_not_called()

    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.handle_resource_error",
    )
    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.invoke_api",
    )
    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.get_resource_params",
        return_value={
            "name": "projects/123123123123/roles/customRole2",
        },
    )
    @mock.patch(
        "c7n_gcp.resources.iam.RoleDeleteAction.get_operation_name",
        return_value="iam.projects.roles.delete",
    )
    def test_handle_role_delete_error(
        self,
        mock_get_op,
        mock_get_params,
        mock_invoke,
        mock_error,
    ):
        override_client = mock.MagicMock()
        model = mock.MagicMock()
        # Assume this resource already went away elsewhere, causing the `HttpError`.
        resource = {
            "name": "projects/123123123123/roles/customRole3",
            "title": "Custom Role",
            "description": "Custom role for testing",
            "includedPermissions": [],
            "stage": "GA",
            "etag": "AwYGhFMnKpQ=",
            "deleted": False,
        }

        # Setup the error to occur.
        mock_resp = {
            "error": {
                "message": "Whoops, it failed.",
            },
        }
        mock_invoke.side_effect = HttpError(
            resp=mock.MagicMock(),
            content=json.dumps(mock_resp).encode("utf-8"),
        )

        # Even with an error, nothing should get raised, & no return value.
        self.rda.handle_role_delete(
            override_client,
            model,
            resource,
            "customRole3",
        )

        # And verify the mocks for correct-looking calls.
        mock_get_op.assert_called_once_with(
            model,
            resource,
        )
        mock_get_params.assert_called_once_with(
            model,
            resource,
        )
        mock_invoke.assert_called_once_with(
            override_client,
            "iam.projects.roles.delete",
            {
                "name": "projects/123123123123/roles/customRole2",
            },
        )
        # Making sure the error was hit, & handling was attempted!
        mock_error.assert_called_once()


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

    @terraform('iam_organization_role')
    def test_iam_role_delete(self):
        org_id = "111111111111"
        role_name = "customAccessContextManagerAdmin"
        full_role_name = f"organizations/{org_id}/roles/{role_name}"

        factory = self.replay_flight_data("iam-role-delete", org_id)

        p = self.load_policy(
            {
                "name": "role-delete",
                "resource": "gcp.iam-role",
                "filters": [{"name": full_role_name}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(1)

        # Get client for organizations.roles to verify deletion
        session = local_session(factory)
        client = session.client('iam', 'v1', 'organizations.roles')

        with pytest.raises(HttpError):
            result = client.execute_query("get", {"name": full_role_name})
            # If role still exists, it should be marked as deleted
            self.assertTrue(result.get("deleted", False), "Role should be marked as deleted")
            # If we're still here, the delete worked.
            # For the sake of a single path of handling, simulate an Http 404
            # error as well, as this is also an acceptable case.
            mock_resp = {
                "error": {
                    "message": "Role not found.",
                },
            }
            raise HttpError(
                resp=mock.MagicMock(status=404),
                content=json.dumps(mock_resp).encode("utf-8"),
            )

    @terraform('iam_project_role')
    def test_iam_role_project_delete(self):
        project_id = "cloud-custodian"
        role_name = "customAccessContextManagerAdmin"
        full_role_name = f"projects/{project_id}/roles/{role_name}"

        factory = self.replay_flight_data("iam-role-delete-proj", project_id)

        p = self.load_policy(
            {
                "name": "role-delete",
                "resource": "gcp.iam-role",
                "filters": [{"name": full_role_name}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(1)

        # Get client for projects.roles to verify deletion
        session = local_session(factory)
        client = session.client('iam', 'v1', 'projects.roles')

        with pytest.raises(HttpError):
            result = client.execute_query("get", {"name": full_role_name})
            # If role still exists, it should be marked as deleted
            self.assertTrue(result.get("deleted", False), "Role should be marked as deleted")
            # If we're still here, the delete worked.
            # For the sake of a single path of handling, simulate an Http 404
            # error as well, as this is also an acceptable case.
            mock_resp = {
                "error": {
                    "message": "Role not found.",
                },
            }
            raise HttpError(
                resp=mock.MagicMock(status=404),
                content=json.dumps(mock_resp).encode("utf-8"),
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
                "filters": [{"type": "time-range", "value": 30}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["name"],
            "projects/cloud-custodian/locations/global/keys/03b651c2-718a-4702-b5d7-9946987cc4da",
        )
