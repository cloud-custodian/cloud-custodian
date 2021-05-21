# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time

from gcp_common import BaseTest, event_data
from googleapiclient.errors import HttpError


class ProjectRoleTest(BaseTest):

    def test_get(self):
        factory = self.replay_flight_data('iam-project-role')

        p = self.load_policy({
            'name': 'role-get',
            'resource': 'gcp.project-role',
            'mode': {
                'type': 'gcp-audit',
                'methods': ['google.iam.admin.v1.CreateRole']}},
            session_factory=factory)

        exec_mode = p.get_execution_mode()
        event = event_data('iam-role-create.json')
        roles = exec_mode.run(event, None)

        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0]['name'], 'projects/cloud-custodian/roles/CustomRole1')


class ServiceAccountTest(BaseTest):

    def test_get(self):
        factory = self.replay_flight_data('iam-service-account')
        p = self.load_policy({
            'name': 'sa-get',
            'resource': 'gcp.service-account'},
            session_factory=factory)
        resource = p.resource_manager.get_resource(
            {'project_id': 'cloud-custodian',
             'email_id': 'devtest@cloud-custodian.iam.gserviceaccount.com',
             'unique_id': '110936229421407410679'})
        self.assertEqual(resource['displayName'], 'devtest')


class ServiceAccountKeyTest(BaseTest):

    def test_service_account_key_query(self):
        project_id = "cloud-custodian"

        session_factory = self.replay_flight_data(
            'iam-service-account-key-query', project_id)

        policy = self.load_policy(
            {
                'name': 'iam-service-account-key-query',
                'resource': 'gcp.service-account-key'
            },
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]["keyType"], "SYSTEM_MANAGED")
        self.assertEqual(resources[1]["keyType"], "USER_MANAGED")

    def test_get_service_account_key(self):
        factory = self.replay_flight_data('iam-service-account-key')
        p = self.load_policy({
            'name': 'sa-key-get',
            'resource': 'gcp.service-account-key'},
            session_factory=factory)
        resource = p.resource_manager.get_resource(
            {'resourceName': '//iam.googleapis.com/projects/cloud-custodian/'
            'serviceAccounts/111111111111111/keys/2222'})
        self.assertEqual(resource['keyType'], 'USER_MANAGED')
        self.assertEqual(resource["c7n:service-account"]["email"],
        "test-cutodian-scc@cloud-custodian.iam.gserviceaccount.com")

    def test_delete_service_account_key(self):
        factory = self.replay_flight_data('iam-delete-service-account-key')
        p = self.load_policy({
            'name': 'sa-key-delete',
            'resource': 'gcp.service-account-key',
            'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(1)
        client = p.resource_manager.get_client()
        try:
            result = client.execute_query(
                'get', {'name': resources[0]["name"]})
            self.fail('found deleted service account key: %s' % result)
        except HttpError as e:
            self.assertTrue("does not exist" in str(e))


class IAMRoleTest(BaseTest):

    def test_iam_role_query(self):
        project_id = "cloud-custodian"

        session_factory = self.replay_flight_data(
            'ami-role-query', project_id)

        policy = self.load_policy(
            {
                'name': 'ami-role-query',
                'resource': 'gcp.iam-role'
            },
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 2)

    def test_iam_role_get(self):
        project_id = 'cloud-custodian'
        name = "accesscontextmanager.policyAdmin"

        session_factory = self.replay_flight_data(
            'ami-role-query-get', project_id)

        policy = self.load_policy(
            {
                'name': 'ami-role-query-get',
                'resource': 'gcp.iam-role'
            },
            session_factory=session_factory)

        resource = policy.resource_manager.get_resource({
            "name": name,
        })

        self.assertEqual(resource['name'], 'roles/{}'.format(name))
