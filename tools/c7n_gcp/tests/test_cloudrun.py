# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest
from c7n.utils import yaml_load


class RunServiceTest(BaseTest):
    def test_query(self):
        factory = self.replay_flight_data("gcp-cloud-run-service")
        p = self.load_policy(
            {"name": "cloud-run-svc", "resource": "gcp.cloud-run-service"},
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]["metadata"]["name"] == "hello"

    def test_set_labels(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data(
            "gcp-cloud-run-service-set-labels", project_id=project_id
        )
        p = self.load_policy(
            {
                'name': 'cloud-run-svc-set-labels',
                'resource': 'gcp.cloud-run-service',
                'filters': [
                    {'type': 'value',
                     'key': 'metadata.name',
                     'value': 'hello'}
                ],
                'actions': [
                    {'type': 'set-labels',
                     'labels': {'environment': 'test'}}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['metadata']['name'] == 'hello'

    def test_filter(self):

        factory = self.replay_flight_data("gcp-cloud-run-service")
        p = self.load_policy(yaml_load(
            """
            name: ensure_gcp_instance_labels
            description: |
              Report resources without labels
            resource: gcp.cloud-run-service
            filters:
             - type: value
               key: metadata.labels."cloud.googleapis.com/location"
               value: us-central1
            """), session_factory=factory)
        resources = p.run()
        assert len(resources) == 1

    def test_cloudrun_filter_iam_query(self):
        project_id = self.project_id
        factory = self.replay_flight_data('gcp-cloud-run-service-filter-iam', project_id=project_id)
        p = self.load_policy({
            'name': 'gcp-cloud-run-service-filter-iam',
            'resource': 'gcp.cloud-run-service',
            'filters': [{
                'type': 'iam-policy',
                'doc': {
                    'key': "bindings[?(role=='roles\\editor' || role=='roles\\owner')]",
                    'op': 'ne',
                    'value': []
                }
            }]
        }, session_factory=factory)
        resources = p.run()

        self.assertEqual(1, len(resources))
        self.assertEqual('run-1',
                         resources[0]["metadata"]['name'])


class JobServiceTest(BaseTest):
    def test_query(self):
        factory = self.replay_flight_data("gcp-cloud-run-job")
        p = self.load_policy(
            {"name": "cloud-run-job", "resource": "gcp.cloud-run-job"},
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]["metadata"]["name"] == "job"

    def test_set_labels(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data(
            "gcp-cloud-run-job-set-labels", project_id=project_id
        )
        p = self.load_policy(
            {
                'name': 'cloud-run-job-set-labels',
                'resource': 'gcp.cloud-run-job',
                'filters': [
                    {'type': 'value',
                     'key': 'metadata.name',
                     'value': 'job'}
                ],
                'actions': [
                    {'type': 'set-labels',
                     'labels': {'environment': 'test'}}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 1
        assert resources[0]['metadata']['name'] == 'job'


class RevisionServiceTest(BaseTest):
    def test_query(self):
        factory = self.replay_flight_data('gcp-cloud-run-revision')
        p = self.load_policy({
            'name': 'cloud-run-job',
            'resource': 'gcp.cloud-run-revision'
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['metadata']['name'], 'hello-00001-nvq')
