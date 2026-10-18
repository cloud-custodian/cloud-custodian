# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest

from freezegun import freeze_time

from gcp_common import BaseTest
from c7n.exceptions import PolicyExecutionError
from c7n.utils import yaml_load

from c7n_gcp.actions.core import MethodAction
from c7n_gcp.resources.cloudrun import CloudRunJob, CloudRunService, knative_body

# The root fields the api accepts, independent of the module under test.
SCHEMA_FIELDS = {'apiVersion', 'kind', 'metadata', 'spec', 'status'}
LOCATION = {'cloud.googleapis.com/location': 'us-central1'}


def listed_resource(api_version, kind, name):
    "A resource as augment() and a value filter leave it once listed."
    return {
        'apiVersion': api_version,
        'kind': kind,
        'metadata': {
            'name': name,
            'namespace': 'cloud-custodian',
            'labels': dict(LOCATION),
        },
        'spec': {'template': {}},
        'status': {'observedGeneration': 1},
        'labels': dict(LOCATION),
        'c7n:MatchedFilters': ['metadata.name'],
    }


def capture_api_params(test):
    """Record the params of every api call the policy's actions make."""
    captured = []
    invoke_api = MethodAction.invoke_api

    def record(action, client, op_name, params):
        captured.append((op_name, params))
        return invoke_api(action, client, op_name, params)

    test.patch(MethodAction, 'invoke_api', record)
    return captured


def assert_replace_body(body, labels):
    "A replace body holds the schema fields and the merged labels, nothing else."
    assert set(body) == SCHEMA_FIELDS
    assert 'labels' not in body
    assert 'c7n:MatchedFilters' not in body
    assert body['metadata']['labels'] == labels


def assert_label_params(model, resource, expected_name):
    "get_label_params addresses the resource and leaves it fit to read again."
    all_labels = dict(LOCATION, environment='test')
    params = model.get_label_params(resource, all_labels)

    assert params['name'] == expected_name
    assert_replace_body(params['body'], all_labels)
    # the action reads its current label state from the resource, so both the
    # synthetic key and the metadata it came from have to survive the call
    assert resource['labels'] == LOCATION
    assert resource['metadata']['labels'] == LOCATION


class KnativeBodyTest(BaseTest):

    def test_keeps_only_the_schema_fields(self):
        body = knative_body({
            'apiVersion': 'serving.knative.dev/v1',
            'kind': 'Service',
            'metadata': {'name': 'hello'},
            'spec': {},
            'status': {},
            'labels': {'env': 'test'},
            'c7n:MatchedFilters': ['metadata.name'],
        })
        assert set(body) == SCHEMA_FIELDS

    def test_drops_annotations_nested_in_spec(self):
        # a list-item filter annotates the objects it matched in place
        body = knative_body({
            'metadata': {'name': 'hello'},
            'spec': {
                'template': {
                    'spec': {
                        'containers': [{
                            'image': 'us-docker.pkg.dev/cloudrun/container/hello',
                            'c7n:MatchedFilters': ['image'],
                        }],
                    },
                },
            },
            'c7n.metrics': {'run.googleapis.com/request_count': []},
        })
        assert body['spec'] == {
            'template': {
                'spec': {
                    'containers': [{
                        'image': 'us-docker.pkg.dev/cloudrun/container/hello'}],
                },
            },
        }

    def test_keeps_user_annotations(self):
        # a kubernetes annotation key may contain a dot, so only the colon form
        # is recognized below the root - a replace deletes what the body omits
        annotations = {
            'run.googleapis.com/ingress': 'all',
            'c7n.example.com/owner': 'platform-team',
        }
        body = knative_body({
            'metadata': {'name': 'hello', 'annotations': dict(annotations)},
            'spec': {'template': {'metadata': {'annotations': dict(annotations)}}},
        })
        assert body['metadata']['annotations'] == annotations
        assert body['spec']['template']['metadata']['annotations'] == annotations

    def test_copies_rather_than_mutates(self):
        resource = {
            'metadata': {'name': 'hello'},
            'spec': {'containers': [{'c7n:MatchedFilters': ['image']}]},
        }
        knative_body(resource)['metadata']['name'] = 'changed'
        assert resource['metadata']['name'] == 'hello'
        assert resource['spec']['containers'][0] == {'c7n:MatchedFilters': ['image']}

    def test_raises_on_fields_outside_the_schema(self):
        with pytest.raises(PolicyExecutionError) as raised:
            knative_body({
                'kind': 'Service',
                'metadata': {'name': 'hello'},
                'somethingNew': 'unrecognized',
            })
        assert 'somethingNew' in str(raised.value)
        assert 'hello' in str(raised.value)

    def test_accepts_the_synthetic_fields(self):
        knative_body({
            'metadata': {'name': 'hello'},
            'labels': {'env': 'test'},
            'c7n:MatchedFilters': ['metadata.name'],
            'c7n.metrics': {'run.googleapis.com/request_count': []},
        })


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

    def test_query_empty(self):
        # regression for #10955: accounts with zero Cloud Run resources must
        # return [] rather than crash. The source layer returns None (not [])
        # for an empty result set, which augment() previously iterated over.
        factory = self.replay_flight_data("gcp-cloud-run-service-empty")
        p = self.load_policy(
            {"name": "cloud-run-svc-empty", "resource": "gcp.cloud-run-service"},
            session_factory=factory,
        )
        resources = p.run()
        assert resources == []

    def test_label_params(self):
        assert_label_params(
            CloudRunService.resource_type,
            listed_resource('serving.knative.dev/v1', 'Service', 'hello'),
            'projects/cloud-custodian/locations/us-central1/services/hello')

    def test_set_labels(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data(
            "gcp-cloud-run-service-set-labels", project_id=project_id
        )
        captured = capture_api_params(self)
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

        assert len(captured) == 1
        op_name, params = captured.pop()
        assert op_name == 'replaceService'
        assert_replace_body(params['body'], {
            'cloud.googleapis.com/location': 'us-central1',
            'environment': 'test',
        })

    @freeze_time("2026-08-19")
    def test_mark_for_op(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data(
            "gcp-cloud-run-service-mark-for-op", project_id=project_id
        )
        captured = capture_api_params(self)
        p = self.load_policy(
            {
                'name': 'cloud-run-svc-mark-for-op',
                'resource': 'gcp.cloud-run-service',
                'filters': [
                    {'type': 'value',
                     'key': 'metadata.name',
                     'value': 'hello'}
                ],
                'actions': [
                    {'type': 'mark-for-op',
                     'op': 'notify',
                     'days': 2}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        assert len(resources) == 1

        assert len(captured) == 1
        op_name, params = captured.pop()
        assert op_name == 'replaceService'
        assert_replace_body(params['body'], {
            'cloud.googleapis.com/location': 'us-central1',
            'custodian_status': 'resource_policy-notify-2026_08_21__0_0',
        })

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

    def test_label_params(self):
        assert_label_params(
            CloudRunJob.resource_type,
            listed_resource('run.googleapis.com/v1', 'Job', 'job'),
            'namespaces/cloud-custodian/jobs/job')

    def test_set_labels(self):
        project_id = 'cloud-custodian'
        factory = self.replay_flight_data(
            "gcp-cloud-run-job-set-labels", project_id=project_id
        )
        captured = capture_api_params(self)
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

        assert len(captured) == 1
        op_name, params = captured.pop()
        assert op_name == 'replaceJob'
        assert_replace_body(params['body'], {
            'cloud.googleapis.com/location': 'us-central1',
            'environment': 'test',
        })


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
