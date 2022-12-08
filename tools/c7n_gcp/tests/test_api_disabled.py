# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest


class ApiDisabledTest(BaseTest):

    def test_app_engine_api_disabled(self):
        project_id = 'cloud-custodian'
        session_factory = self.replay_flight_data(
            'app-engine-api-disabled', project_id=project_id)

        policy = self.load_policy(
            {'name': 'gcp-app-engine-disabled',
             'resource': 'gcp.app-engine'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 0)

    def test_dataflow_api_disabled(self):
        project_id = 'cloud-custodian'
        session_factory = self.replay_flight_data(
            'dataflow-api-disabled', project_id=project_id)

        policy = self.load_policy(
            {'name': 'dataflow-job',
             'resource': 'gcp.dataflow-job'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 0)

    def test_spanner_api_disabled(self):
        project_id = 'cloud-custodian'
        session_factory = self.replay_flight_data(
            'spanner-api-disabled', project_id=project_id)

        policy = self.load_policy(
            {'name': 'all-spanner-instances',
             'resource': 'gcp.spanner-instance'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 0)

    def test_sql_api_disabled(self):
        project_id = 'cloud-custodian'
        session_factory = self.replay_flight_data(
            'sql-api-disabled', project_id=project_id)

        policy = self.load_policy(
            {'name': 'all-sqlinstances',
             'resource': 'gcp.sql-instance'},
            session_factory=session_factory)

        resources = policy.run()
        self.assertEqual(len(resources), 0)
