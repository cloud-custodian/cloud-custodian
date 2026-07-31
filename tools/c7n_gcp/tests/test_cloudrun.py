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

    def test_get_metric_resource_name_revision_name(self):
        """Test extraction of revision name for metrics filtering"""
        from c7n_gcp.resources.cloudrun import CloudRunRevision

        sample_resource = {
            'metadata': {
                'name': 'myservice-00015-kkr',
                'namespace': '123456789',
                'labels': {
                    'serving.knative.dev/service': 'myservice',
                    'cloud.googleapis.com/location': 'us-central1'
                }
            }
        }

        result = CloudRunRevision.resource_type.get_metric_resource_name(
            sample_resource,
            metric_key='resource.labels.revision_name'
        )
        self.assertEqual(result, 'myservice-00015-kkr')
        self.assertIsNotNone(result)

    def test_get_metric_resource_name_service_name(self):
        """Test extraction of service name for metrics filtering"""
        from c7n_gcp.resources.cloudrun import CloudRunRevision

        sample_resource = {
            'metadata': {
                'name': 'myservice-00015-kkr',
                'namespace': '123456789',
                'labels': {
                    'serving.knative.dev/service': 'myservice',
                    'cloud.googleapis.com/location': 'us-central1'
                }
            }
        }

        result = CloudRunRevision.resource_type.get_metric_resource_name(
            sample_resource,
            metric_key='resource.labels.service_name'
        )
        self.assertEqual(result, 'myservice')
        self.assertIsNotNone(result)

    def test_get_metric_resource_name_default(self):
        """Test default behavior (returns revision name)"""
        from c7n_gcp.resources.cloudrun import CloudRunRevision

        sample_resource = {
            'metadata': {
                'name': 'myservice-00015-kkr',
                'namespace': '123456789',
                'labels': {
                    'serving.knative.dev/service': 'myservice'
                }
            }
        }

        result = CloudRunRevision.resource_type.get_metric_resource_name(
            sample_resource,
            metric_key=None
        )
        self.assertEqual(result, 'myservice-00015-kkr')

        result = CloudRunRevision.resource_type.get_metric_resource_name(sample_resource)
        self.assertEqual(result, 'myservice-00015-kkr')

    def test_get_metric_resource_name_handles_nested_structure(self):
        """Test that nested metadata.name is correctly extracted (not None)"""
        from c7n_gcp.resources.cloudrun import CloudRunRevision

        sample_resource = {
            'metadata': {
                'name': 'test-revision-abc-123',
                'namespace': '999999999'
            }
        }

        result = CloudRunRevision.resource_type.get_metric_resource_name(sample_resource)
        self.assertIsNotNone(result)
        self.assertEqual(result, 'test-revision-abc-123')
        self.assertNotEqual(result, 'None')
