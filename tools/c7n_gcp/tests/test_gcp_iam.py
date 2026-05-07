# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time

from gcp_common import BaseTest, event_data
from googleapiclient.errors import HttpError
from pytest_terraform import terraform


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


@terraform("api_key_audit")
def test_api_key_get_audit_mode(test, api_key_audit):
    # export TF_VAR_GCP_PROJECT_ID variable prior to running functional test
    api_key = api_key_audit.resources['google_apikeys_key']['api_key']
    short_key_name = api_key['name']
    project_id = api_key['project']
    factory = test.replay_flight_data('api-key-create')
    p = test.load_policy(
        {
            'name': 'api-key-get',
            'resource': 'gcp.api-key',
            'mode': {
                'type': 'gcp-audit',
                'methods': ['google.api.apikeys.v2.ApiKeys.CreateKey'],
            },
        },
        session_factory=factory,
    )
    exec_mode = p.get_execution_mode()
    event = {
        'protoPayload': {
            'resourceName': f'projects/{project_id}/locations/global/keys/{short_key_name}',
        },
        'resource': {
            'labels': {},
        },
    }
    keys = exec_mode.run(event, None)
    assert len(keys) == 1
    assert keys[0]['name'].endswith(f'/keys/{short_key_name}')
    assert 'restrictions' in keys[0]


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


@terraform("api_key_patch")
def test_api_key_patch_restrictions_and_annotations(test, api_key_patch):
    short_key_name = api_key_patch.resources['google_apikeys_key']['api_key']['name']
    factory = test.replay_flight_data('api-key-patch')
    policy = test.load_policy(
        {
            'name': 'api-key-patch',
            'resource': 'gcp.api-key',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value': f'*/{short_key_name}',
                }
            ],
            'actions': [
                {
                    'type': 'patch',
                    'restrictions': {
                        'serverKeyRestrictions': {
                            'allowedIps': ['192.0.2.0/24'],
                        },
                        'apiTargets': [
                            {'service': 'translate.googleapis.com'},
                        ],
                    },
                    'annotations': {
                        'custodian-remediated': 'true',
                    },
                }
            ],
        },
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1
    actual_key_name = resources[0]['name']

    client = policy.resource_manager.get_client()
    for _ in range(10):
        updated_key = client.execute_query('get', {'name': actual_key_name})
        if 'restrictions' in updated_key:
            break
        time.sleep(3)

    assert 'restrictions' in updated_key
    assert 'serverKeyRestrictions' in updated_key['restrictions']
    assert '192.0.2.0/24' in updated_key['restrictions']['serverKeyRestrictions']['allowedIps']
    assert {'service': 'translate.googleapis.com'} in updated_key['restrictions']['apiTargets']
    assert updated_key.get('annotations', {}).get('custodian-remediated') == 'true'


@terraform("api_key_delete")
def test_api_key_delete(test, api_key_delete):
    short_key_name = api_key_delete.resources['google_apikeys_key']['api_key']['name']
    factory = test.replay_flight_data('api-key-delete')

    policy = test.load_policy(
        {
            'name': 'api-key-delete',
            'resource': 'gcp.api-key',
            'filters': [
                {'type': 'value', 'key': 'name', 'op': 'glob',
                 'value': f'*/{short_key_name}'},
            ],
            'actions': ['delete'],
        },
        session_factory=factory,
    )

    resources = policy.run()
    assert len(resources) == 1
    actual_key_name = resources[0]['name']

    client = policy.resource_manager.get_client()
    parent = actual_key_name.rsplit('/keys/', 1)[0]
    remaining = client.execute_query('list', {'parent': parent})
    assert actual_key_name not in [k['name'] for k in remaining.get('keys', [])]
