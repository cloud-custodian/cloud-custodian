# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os
import json
import time
import logging
from unittest.mock import Mock, patch
from google.api_core.client_options import ClientOptions
from c7n.testing import C7N_FUNCTIONAL
from c7n_gcp.client import get_default_project
from c7n.config import Config
from gcp_common import BaseTest


def get_test_model_id(project_id, location):
    """Get full model resource name for testing.

    Uses the model ID from environment variable and constructs the full
    resource path for the specified location.

    Args:
        project_id: GCP project ID
        location: GCP location (e.g., 'us-central1')

    Returns:
        Full model resource path

    Raises:
        RuntimeError: If the required environment variable is not set
    """
    ENV_VARS = {
        'us-central1': 'GCP_VERTEX_AI_TEST_MODEL_ID_CENTRAL',
        'us-east1': 'GCP_VERTEX_AI_TEST_MODEL_ID_EAST'
    }

    env_var = ENV_VARS[location]
    if env_var not in os.environ:
        raise RuntimeError(
            f'Environment variable {env_var} is required for testing.\n'
            f'Set it to a valid model ID:\n'
            f'  export {env_var}="<ID>"'
        )

    model_id = os.environ[env_var]
    full_path = f'projects/{project_id}/locations/{location}/models/{model_id}'
    return full_path


def poll_for_state(
    policy,
    expected_states,
    test,
    max_attempts=6,
    wait_seconds=10,
    description='state change'
):
    """Poll a policy until resources reach expected state(s).

    Args:
        policy: Cloud Custodian policy to run
        expected_states: List of acceptable states (e.g., ['JOB_STATE_RUNNING'])
        test: Test fixture with recording attribute
        max_attempts: Maximum number of polling attempts
        wait_seconds: Seconds to wait between attempts (only in recording mode)
        description: Human-readable description for logging

    Returns:
        List of resources that match the expected states

    Raises:
        AssertionError: If no resources found or states don't match after all attempts
    """
    print(f'\nPolling for {description}...')
    resources = None

    for attempt in range(1, max_attempts + 1):
        print(f'  Check {attempt}/{max_attempts}:')

        # Only sleep in recording mode; replay uses recorded responses
        if test.recording:
            print(f'    Waiting {wait_seconds} seconds...')
            time.sleep(wait_seconds)

        resources = policy.run()

        if resources:
            current_state = resources[0].get('state')
            print(f'    Current state: {current_state}')

            if current_state in expected_states:
                print('    ✓ Reached expected state')
                break
        else:
            print('    No resources found')

    # Verify we got resources in the expected state
    if not resources:
        raise AssertionError(f'No resources found after {max_attempts} attempts')

    states = [r.get('state') for r in resources]
    if not all(r['state'] in expected_states for r in resources):
        raise AssertionError(
            f'Expected states {expected_states}, got: {states}'
        )

    return resources


def test_vertexai_endpoint_multi_location(test):
    """Test querying Vertex AI Endpoints across multiple locations.

    This test verifies that we can query endpoints in multiple locations
    in a single policy run by specifying multiple locations in the query.
    """

    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-endpoint-multi-location', project_id=project_id)
    else:
        session_factory = test.replay_flight_data('vertexai-endpoint-multi-location')

    # Query both us-central1 and us-east1 in a single policy
    policy = test.load_policy(
        {'name': 'vertexai-endpoints-multi-location',
         'resource': 'gcp.vertex-ai-endpoint',
         'query': [
             {'location': 'us-central1'},
             {'location': 'us-east1'}
         ]},
        session_factory=session_factory)

    resources = policy.run()

    # Should find endpoints from both locations
    assert len(resources) >= 2

    # Verify we have resources from both locations
    locations = {r['name'].split('/')[3] for r in resources}
    assert 'us-central1' in locations
    assert 'us-east1' in locations

    # Verify each resource has the c7n:location annotation
    assert all('c7n:location' in r for r in resources)


def test_vertexai_endpoint_get_urns(test):
    """Test URN generation for Vertex AI Endpoints.

    This test verifies that URNs are correctly generated for Vertex AI endpoints,
    which exercises the _get_location classmethod to extract location from resource names.
    """
    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-endpoint-multi-location', project_id=project_id)
    else:
        session_factory = test.replay_flight_data('vertexai-endpoint-multi-location')

    policy = test.load_policy({
        'name': 'test-endpoint-urns',
        'resource': 'gcp.vertex-ai-endpoint',
        'query': [
            {'location': 'us-central1'}
        ]
    }, session_factory=session_factory)

    resources = policy.run()
    assert len(resources) >= 1

    # Get URNs for the resources - this calls _get_location
    urns = policy.resource_manager.get_urns(resources)

    # Verify URN format: gcp:aiplatform:us-central1:project:endpoint/id
    assert len(urns) == len(resources)
    for urn in urns:
        assert urn.startswith('gcp:aiplatform:us-central1:')
        assert ':endpoint/' in urn


def test_vertexai_endpoint_filtering(test,):
    """Test filtering Vertex AI Endpoints on common fields.

    This test explicitly verifies that value filters work correctly on
    endpoint displayName field.
    """
    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-endpoint-filtering', project_id=project_id)
    else:
        session_factory = test.replay_flight_data('vertexai-endpoint-filtering')

    # Filter by displayName using regex
    policy = test.load_policy(
        {'name': 'filter-by-display-name',
         'resource': 'gcp.vertex-ai-endpoint',
         'query': [
             {'location': 'us-central1'},
             {'location': 'us-east1'}
         ],
         'filters': [
             {'type': 'value',
              'key': 'displayName',
              'op': 'regex',
              'value': '.*-central$'}
         ]},
        session_factory=session_factory)

    resources = policy.run()

    # Should only find endpoints with names ending in '-central'
    assert len(resources) >= 1
    assert all(r['displayName'].endswith('-central') for r in resources)


def test_vertexai_endpoint_delete(test):
    """Test deleting Vertex AI Endpoints.

    This test verifies that the delete action can successfully delete
    endpoints across multiple locations.
    """
    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-endpoint-delete', project_id=project_id)
    else:
        session_factory = test.replay_flight_data('vertexai-endpoint-delete')

    policy = test.load_policy(
        {'name': 'delete-test-endpoints',
         'resource': 'gcp.vertex-ai-endpoint',
         'query': [
             {'location': 'us-central1'}
         ],
         'filters': [
             {'type': 'value',
              'key': 'displayName',
              'op': 'regex',
              'value': 'c7n-.*'}
         ],
         'actions': [
             {'type': 'delete'}
         ]},
        session_factory=session_factory)

    resources = policy.run()

    # Verify that resources were found and deleted
    assert len(resources) >= 1

    # Verify all resources have the expected naming pattern
    assert all('c7n-' in r.get('displayName', '') for r in resources)

    # Re-query to verify the endpoint was actually deleted
    if test.recording:
        time.sleep(1)

    verify_policy = test.load_policy(
        {'name': 'verify-deletion',
         'resource': 'gcp.vertex-ai-endpoint',
         'query': [
             {'location': 'us-central1'}
         ],
         'filters': [
             {'type': 'value',
              'key': 'displayName',
              'op': 'regex',
              'value': 'c7n-.*'}
         ]},
        session_factory=session_factory)

    remaining_resources = verify_policy.run()

    # Verify that the endpoint no longer exists
    assert len(remaining_resources) == 0


def test_vertexai_endpoint_monitor(test):
    """Test creating Model Deployment Monitoring Jobs for Vertex AI Endpoints.

    This test verifies that the monitor action can successfully create
    monitoring jobs for endpoints with deployed models across multiple regions.
    It also tests that running the action again does not fail.
    """
    if C7N_FUNCTIONAL:
        session_factory = test.record_flight_data('vertexai-endpoint-monitor')
        # In functional mode, use the actual GCS bucket
        session = session_factory()
        project_id = session.get_default_project()
        schema_uri = f'gs://{project_id}-vertex-test-models/schema/instance_schema.yaml'
    else:
        session_factory = test.replay_flight_data('vertexai-endpoint-monitor')
        # In replay mode, use a placeholder schema URI (won't actually be accessed)
        schema_uri = 'gs://cloud-custodian-vertex-test-models/schema/instance_schema.yaml'

    policy = test.load_policy(
        {'name': 'monitor-endpoints',
         'resource': 'gcp.vertex-ai-endpoint',
         'query': [
             {'location': 'us-central1'},
             {'location': 'us-east1'}
         ],
         'filters': [
             {'type': 'value',
              'key': 'deployedModels',
              'value': 'present'}
         ],
         'actions': [
             {'type': 'monitor',
              'analysis_instance_schema_uri': schema_uri}
         ]},
        session_factory=session_factory)

    resources = policy.run()

    # Verify that resources were found in both regions
    assert len(resources) >= 2

    # Verify all resources have deployed models
    assert all(r.get('deployedModels') for r in resources)

    locations = {r['name'].split('/')[3] for r in resources}
    assert 'us-central1' in locations
    assert 'us-east1' in locations

    session = session_factory()
    project_id = session.get_default_project()

    # Check both regions
    regions = ['us-central1', 'us-east1']
    total_c7n_jobs = 0

    for region in regions:
        # Query for the monitoring job we just created
        client_options = ClientOptions(
            api_endpoint=f'https://{region}-aiplatform.googleapis.com'
        )
        monitoring_client = session.client(
            'aiplatform', 'v1',
            'projects.locations.modelDeploymentMonitoringJobs',
            client_options=client_options
        )

        # List monitoring jobs
        response = monitoring_client.execute_command(
            'list',
            {'parent': f'projects/{project_id}/locations/{region}'}
        )

        monitoring_jobs = response.get('modelDeploymentMonitoringJobs', [])

        # Count monitoring jobs with c7n naming pattern
        c7n_jobs = [
            job for job in monitoring_jobs
            if job.get('displayName', '').startswith('c7n-monitor-')
        ]
        total_c7n_jobs += len(c7n_jobs)

        # Verify at least one monitoring job exists in this region
        assert len(c7n_jobs) >= 1, f'No monitoring jobs found in {region}'

    # Verify we have monitoring jobs in both regions
    assert total_c7n_jobs >= 2

    # Test idempotency: Run the monitor action again
    # wait 30 seconds to allow the monitoring job to enter running state
    if C7N_FUNCTIONAL:
        time.sleep(30)
    log_output = test.capture_logging('custodian.actions', level=logging.WARNING)
    resources_retry = policy.run()
    assert len(resources_retry) >= 2

    # Verify we emit the expected warning when monitoring jobs already exist.
    logs = log_output.getvalue()
    assert 'Monitoring job already exists for endpoint' in logs


def test_vertexai_endpoint_monitor_no_schema(test):
    """Test creating Model Deployment Monitoring Jobs without schema URI.

    This test verifies that the monitor action works when no schema URI is provided.
    The monitoring job will be created but will remain in PENDING state until
    ~1000 prediction requests are received.
    """
    # Reuse the existing cassette since the API calls are the same
    session_factory = test.replay_flight_data('vertexai-endpoint-monitor')

    policy = test.load_policy(
        {'name': 'monitor-endpoints-no-schema',
         'resource': 'gcp.vertex-ai-endpoint',
         'query': [
             {'location': 'us-central1'}
         ],
         'filters': [
             {'type': 'value',
              'key': 'deployedModels',
              'value': 'present'}
         ],
         'actions': [
             {'type': 'monitor'}
         ]},
        session_factory=session_factory
    )

    log_output = test.capture_logging('custodian.actions', level=logging.WARNING)
    resources = policy.run()

    # Should still find endpoints and process the action without schema.
    assert len(resources) >= 1
    assert all(r.get('deployedModels') for r in resources)

    # Verify we emit the expected warning about missing schema.
    logs = log_output.getvalue()
    assert 'No analysis_instance_schema_uri provided.' in logs
    assert 'will remain in PENDING state' in logs


# Batch Prediction Job Tests
# Before running any of these test in recording mode. Complete the steps in
# tools/c7n_gcp/tests/terraform/vertexai_batch_prediction_job/vertex_batch.md to create the
# necessary test resources.

def test_vertexai_batch_prediction_job_multi_location(test):
    """Test querying Vertex AI Batch Prediction Jobs across multiple locations.

    This test verifies that we can query batch prediction jobs in multiple locations
    in a single policy run by specifying multiple locations in the query.
    """
    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-batch-prediction-job-multi-location', project_id=project_id)
    else:
        session_factory = test.replay_flight_data(
            'vertexai-batch-prediction-job-multi-location')

    # When recording, create batch prediction jobs via API
    if test.recording:
        session = session_factory()
        project_id = session.get_default_project()

        # Get terraform outputs from tf_resources.json
        tf_dir = os.path.join(
            os.path.dirname(__file__),
            'terraform/vertexai_batch_prediction_job'
        )
        tf_resources_file = os.path.join(tf_dir, 'tf_resources.json')

        with open(tf_resources_file, 'r') as f:
            tf_data = json.load(f)

        # Extract outputs
        outputs = tf_data['outputs']
        input_uri_us_central1 = outputs['input_uri_us_central1']['value']
        input_uri_us_east1 = outputs['input_uri_us_east1']['value']
        output_uri_us_central1 = outputs['output_uri_us_central1']['value']
        output_uri_us_east1 = outputs['output_uri_us_east1']['value']

        # Create batch prediction job in us-central1
        client_options_central = ClientOptions(
            api_endpoint='https://us-central1-aiplatform.googleapis.com'
        )
        client_central = session.client(
            'aiplatform', 'v1',
            'projects.locations.batchPredictionJobs',
            client_options=client_options_central
        )

        model_id_central = get_test_model_id(project_id, 'us-central1')

        job_config_central = {
            'displayName': 'c7n-test-batch-job-central',
            'model': model_id_central,
            'inputConfig': {
                'instancesFormat': 'jsonl',
                'gcsSource': {
                    'uris': [input_uri_us_central1]
                }
            },
            'outputConfig': {
                'predictionsFormat': 'jsonl',
                'gcsDestination': {
                    'outputUriPrefix': output_uri_us_central1
                }
            },
            'dedicatedResources': {
                'machineSpec': {
                    'machineType': 'n1-standard-2'
                },
                'startingReplicaCount': 1
            }
        }

        client_central.execute_command(
            'create',
            {
                'parent': f'projects/{project_id}/locations/us-central1',
                'body': job_config_central
            }
        )

        # Create batch prediction job in us-east1
        client_options_east = ClientOptions(
            api_endpoint='https://us-east1-aiplatform.googleapis.com'
        )
        client_east = session.client(
            'aiplatform', 'v1',
            'projects.locations.batchPredictionJobs',
            client_options=client_options_east
        )

        model_id_east = get_test_model_id(project_id, 'us-east1')

        job_config_east = {
            'displayName': 'c7n-test-batch-job-east',
            'model': model_id_east,
            'inputConfig': {
                'instancesFormat': 'jsonl',
                'gcsSource': {
                    'uris': [input_uri_us_east1]
                }
            },
            'outputConfig': {
                'predictionsFormat': 'jsonl',
                'gcsDestination': {
                    'outputUriPrefix': output_uri_us_east1
                }
            },
            'dedicatedResources': {
                'machineSpec': {
                    'machineType': 'n1-standard-2'
                },
                'startingReplicaCount': 1
            }
        }

        client_east.execute_command(
            'create',
            {
                'parent': f'projects/{project_id}/locations/us-east1',
                'body': job_config_east
            }
        )

    # Query both us-central1 and us-east1 in a single policy
    policy = test.load_policy(
        {'name': 'vertexai-batch-jobs-multi-location',
         'resource': 'gcp.vertex-ai-batch-prediction-job',
         'query': [
             {'location': 'us-central1'},
             {'location': 'us-east1'}
         ]},
        session_factory=session_factory)

    resources = policy.run()

    # Should find batch jobs from both locations
    assert len(resources) >= 2

    # Verify we have resources from both locations
    locations = {r['name'].split('/')[3] for r in resources}
    assert 'us-central1' in locations
    assert 'us-east1' in locations


def test_vertexai_batch_prediction_job_filtering(test):
    """Test filtering Vertex AI Batch Prediction Jobs on state.

    This test verifies that value filters work correctly on batch job state field.
    It filters for jobs in JOB_STATE_RUNNING state.
    """
    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-batch-prediction-job-filtering', project_id=project_id)
    else:
        session_factory = test.replay_flight_data(
            'vertexai-batch-prediction-job-filtering')

    # When recording, create batch prediction jobs via API
    if test.recording:
        session = session_factory()
        project_id = session.get_default_project()

        # Get terraform outputs from tf_resources.json
        tf_dir = os.path.join(
            os.path.dirname(__file__),
            'terraform/vertexai_batch_prediction_job'
        )
        tf_resources_file = os.path.join(tf_dir, 'tf_resources.json')

        with open(tf_resources_file, 'r') as f:
            tf_data = json.load(f)

        # Extract outputs
        outputs = tf_data['outputs']
        input_uri_us_central1 = outputs['input_uri_us_central1']['value']
        output_uri_us_central1 = outputs['output_uri_us_central1']['value']

        # Create batch prediction job in us-central1
        client_options_central = ClientOptions(
            api_endpoint='https://us-central1-aiplatform.googleapis.com'
        )
        client_central = session.client(
            'aiplatform', 'v1',
            'projects.locations.batchPredictionJobs',
            client_options=client_options_central
        )

        model_id_central = get_test_model_id(project_id, 'us-central1')

        job_config_central = {
            'displayName': 'c7n-test-batch-job-filter',
            'model': model_id_central,
            'inputConfig': {
                'instancesFormat': 'jsonl',
                'gcsSource': {
                    'uris': [input_uri_us_central1]
                }
            },
            'outputConfig': {
                'predictionsFormat': 'jsonl',
                'gcsDestination': {
                    'outputUriPrefix': output_uri_us_central1
                }
            },
            'dedicatedResources': {
                'machineSpec': {
                    'machineType': 'n1-standard-2'
                },
                'startingReplicaCount': 1
            }
        }

        client_central.execute_command(
            'create',
            {
                'parent': f'projects/{project_id}/locations/us-central1',
                'body': job_config_central
            }
        )

    # Filter by state - looking for running jobs
    policy = test.load_policy(
        {'name': 'filter-by-state',
         'resource': 'gcp.vertex-ai-batch-prediction-job',
         'query': [
             {'location': 'us-central1'}
         ],
         'filters': [
             {'type': 'value',
              'key': 'state',
              'value': 'JOB_STATE_RUNNING'}
         ]},
        session_factory=session_factory)

    resources = policy.run()

    # When recording, should find the job we just created in running state
    # When replaying, verify all returned jobs are in running state
    if len(resources) > 0:
        assert all(r['state'] == 'JOB_STATE_RUNNING' for r in resources)


def test_vertexai_batch_prediction_job_get_urns(test):
    """Test URN generation for Vertex AI Batch Prediction Jobs.

    This test verifies that URNs are correctly generated for batch prediction jobs,
    which exercises the _get_location classmethod to extract location from resource names.
    """
    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-batch-prediction-job-multi-location', project_id=project_id)
    else:
        session_factory = test.replay_flight_data(
            'vertexai-batch-prediction-job-multi-location')

    policy = test.load_policy({
        'name': 'test-batch-job-urns',
        'resource': 'gcp.vertex-ai-batch-prediction-job',
        'query': [
            {'location': 'us-central1'}
        ]
    }, session_factory=session_factory)

    resources = policy.run()
    assert len(resources) >= 1

    # Get URNs for the resources - this calls _get_location
    urns = policy.resource_manager.get_urns(resources)

    # Verify URN format: gcp:aiplatform:us-central1:project:batch-prediction-job/id
    assert len(urns) == len(resources)
    for urn in urns:
        assert urn.startswith('gcp:aiplatform:us-central1:')
        assert ':batch-prediction-job/' in urn


# This test covers both stopping and deleting batch prediction jobs since they are closely related
# and both require waiting for state changes to take effect before the next action can be performed.
# if anything goes wrong during test execution it can leave behind test jobs which can cause
# recording failures due to duplicate job names having a state of failed. If this occurs, use the
# cleanup script in tests/scripts/cleanup_vertex_ai_batch_jobs.py to delete any leftover test jobs
# before re-recording the test.

def test_vertexai_batch_prediction_job_stop_and_delete(test):
    """Test stopping and deleting Vertex AI Batch Prediction Jobs.

    This test verifies that:
    1. A running batch prediction job can be stopped (cancelled)
    2. The stopped job can then be deleted
    """
    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-batch-prediction-job-stop-and-delete', project_id=project_id)
    else:
        session_factory = test.replay_flight_data(
            'vertexai-batch-prediction-job-stop-and-delete')

    # When recording, create a batch prediction job to stop and delete
    if test.recording:
        session = session_factory()
        project_id = session.get_default_project()

        # Get terraform outputs from tf_resources.json
        tf_dir = os.path.join(
            os.path.dirname(__file__),
            'terraform/vertexai_batch_prediction_job'
        )
        tf_resources_file = os.path.join(tf_dir, 'tf_resources.json')

        with open(tf_resources_file, 'r') as f:
            tf_data = json.load(f)

        # Extract outputs
        outputs = tf_data['outputs']
        input_uri_us_central1 = outputs['input_uri_us_central1']['value']
        output_uri_us_central1 = outputs['output_uri_us_central1']['value']

        # Create batch prediction job in us-central1
        client_options_central = ClientOptions(
            api_endpoint='https://us-central1-aiplatform.googleapis.com'
        )
        client_central = session.client(
            'aiplatform', 'v1',
            'projects.locations.batchPredictionJobs',
            client_options=client_options_central
        )

        model_id_central = get_test_model_id(project_id, 'us-central1')

        job_config = {
            'displayName': 'c7n-test-stop-delete-job',
            'model': model_id_central,
            'inputConfig': {
                'instancesFormat': 'jsonl',
                'gcsSource': {
                    'uris': [input_uri_us_central1]
                }
            },
            'outputConfig': {
                'predictionsFormat': 'jsonl',
                'gcsDestination': {
                    'outputUriPrefix': output_uri_us_central1
                }
            },
            'dedicatedResources': {
                'machineSpec': {
                    'machineType': 'n1-standard-2'
                },
                'startingReplicaCount': 1
            }
        }

        response = client_central.execute_command(
            'create',
            {
                'parent': f'projects/{project_id}/locations/us-central1',
                'body': job_config
            }
        )

        print('\nJob created:')
        print(f'  Name: {response.get("name")}')
        print(f'  Display Name: {response.get("displayName")}')
        print(f'  Initial State: {response.get("state")}')

        # Wait for job to transition to running state
        check_running_policy = test.load_policy(
            {'name': 'check-running',
             'resource': 'gcp.vertex-ai-batch-prediction-job',
             'query': [
                 {'location': 'us-central1'}
             ],
             'filters': [
                 {'type': 'value',
                  'key': 'displayName',
                  'value': 'c7n-test-stop-delete-job'}
             ]},
            session_factory=session_factory)

        poll_for_state(
            check_running_policy,
            ['JOB_STATE_RUNNING'],
            test,
            description='job to start running'
        )

    # Step 1: Stop the running job
    stop_filters = [
        {'type': 'value',
         'key': 'state',
         'value': 'JOB_STATE_RUNNING'},
        {'type': 'value',
         'key': 'displayName',
         'value': 'c7n-test-stop-delete-job'}
    ]

    stop_policy = test.load_policy(
        {'name': 'stop-running-batch-jobs',
         'resource': 'gcp.vertex-ai-batch-prediction-job',
         'query': [
             {'location': 'us-central1'}
         ],
         'filters': stop_filters,
         'actions': [
             {'type': 'stop'}
         ]},
        session_factory=session_factory)

    stopped_resources = stop_policy.run()
    assert len(stopped_resources) >= 1, 'No running jobs found to stop'

    # Step 2: Wait for the stop action to take effect and verify cancellation
    verify_filters = [
        {'type': 'value',
         'key': 'displayName',
         'value': 'c7n-test-stop-delete-job'}
    ]

    verify_stop_policy = test.load_policy(
        {'name': 'verify-cancellation',
         'resource': 'gcp.vertex-ai-batch-prediction-job',
         'query': [
             {'location': 'us-central1'}
         ],
         'filters': verify_filters},
        session_factory=session_factory)

    cancelled_resources = poll_for_state(
        verify_stop_policy,
        ['JOB_STATE_CANCELLED', 'JOB_STATE_CANCELLING'],
        test,
        description='stop action to take effect'
    )

    # Wait for job to fully transition to CANCELLED (not just CANCELLING)
    # Jobs in CANCELLING state cannot be deleted
    # This runs in both recording and replay modes to consume all recorded API calls
    if cancelled_resources and cancelled_resources[0].get('state') == 'JOB_STATE_CANCELLING':
        recheck_filters = [
            {'type': 'value',
             'key': 'displayName',
             'value': 'c7n-test-stop-delete-job'}
        ]

        recheck_policy = test.load_policy(
            {'name': 'recheck-cancelled-state',
             'resource': 'gcp.vertex-ai-batch-prediction-job',
             'query': [
                 {'location': 'us-central1'}
             ],
             'filters': recheck_filters},
            session_factory=session_factory)

        poll_for_state(
            recheck_policy,
            ['JOB_STATE_CANCELLED'],
            test,
            description='full cancellation (CANCELLING → CANCELLED)'
        )

    # Step 3: Delete the cancelled job
    delete_filters = [
        {'type': 'value',
         'key': 'displayName',
         'value': 'c7n-test-stop-delete-job'}
    ]

    delete_policy = test.load_policy(
        {'name': 'delete-cancelled-batch-jobs',
         'resource': 'gcp.vertex-ai-batch-prediction-job',
         'query': [
             {'location': 'us-central1'}
         ],
         'filters': delete_filters,
         'actions': [
             {'type': 'delete'}
         ]},
        session_factory=session_factory)

    deleted_resources = delete_policy.run()

    # Verify that the job was found and deleted
    assert len(deleted_resources) >= 1

    # Wait for deletion to complete
    if test.recording:
        print('Waiting for deletion to complete...')
        time.sleep(5)

    # Step 4: Verify the job no longer exists
    verify_delete_filters = [
        {'type': 'value',
         'key': 'displayName',
         'value': 'c7n-test-stop-delete-job'}
    ]

    verify_delete_policy = test.load_policy(
        {'name': 'verify-deletion',
         'resource': 'gcp.vertex-ai-batch-prediction-job',
         'query': [
             {'location': 'us-central1'}
         ],
         'filters': verify_delete_filters},
        session_factory=session_factory)

    remaining_resources = verify_delete_policy.run()

    # Verify that the job no longer exists
    assert len(remaining_resources) == 0


def test_vertexai_endpoint_location_query_with_location(test):
    """Test location specification via query with 'location' key.

    This test verifies that endpoints can be queried from specific locations
    using the 'location' key in the query specification.
    """
    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-endpoint-location-query-location',
            project_id=project_id
        )
    else:
        session_factory = test.replay_flight_data('vertexai-endpoint-location-query-location')

    policy = test.load_policy({
        'name': 'test-location-query-location',
        'resource': 'gcp.vertex-ai-endpoint',
        'query': [
            {'location': 'us-central1'},
            {'location': 'us-east1'}
        ]
    }, session_factory=session_factory)

    resources = policy.run()

    # Verify resources are only from the queried locations
    if resources:
        locations = {r['name'].split('/')[3] for r in resources}
        # All resources should be from the queried locations
        assert locations.issubset({'us-central1', 'us-east1'})


def test_vertexai_endpoint_location_config_region_singular(test):
    """Test location specification via config region (singular).

    This test verifies that endpoints can be queried from a single location
    using the --region config parameter (singular, not plural).
    """
    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-endpoint-location-config-region', project_id=project_id)
    else:
        session_factory = test.replay_flight_data(
            'vertexai-endpoint-location-config-region')

    config = Config.empty(region='us-central1')

    policy = test.load_policy({
        'name': 'test-location-config-region',
        'resource': 'gcp.vertex-ai-endpoint'
    }, session_factory=session_factory, config=config)

    resources = policy.run()

    # Verify resources are only from the config region
    if resources:
        locations = {r['name'].split('/')[3] for r in resources}
        # All resources should be from us-central1
        assert locations == {'us-central1'}


def test_vertexai_endpoint_location_config_regions(test):
    """Test location specification via config regions.

    This test verifies that endpoints can be queried from specific locations
    using the --regions config parameter.
    """

    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-endpoint-location-config-regions', project_id=project_id)
    else:
        session_factory = test.replay_flight_data(
            'vertexai-endpoint-location-config-regions')

    config = Config.empty(regions=['us-central1', 'us-west1'])

    policy = test.load_policy({
        'name': 'test-location-config-regions',
        'resource': 'gcp.vertex-ai-endpoint'
    }, session_factory=session_factory, config=config)

    resources = policy.run()

    # Verify resources are only from the config regions
    if resources:
        locations = {r['name'].split('/')[3] for r in resources}
        # All resources should be from the config regions
        assert locations.issubset({'us-central1', 'us-west1'})


def test_vertexai_endpoint_location_default_all_regions(test):
    """Test default location behavior (all Vertex AI regions).

    This test verifies that when no query or config is specified,
    endpoints are queried from all Vertex AI supported regions.
    """
    if C7N_FUNCTIONAL:
        project_id = get_default_project()
        session_factory = test.record_flight_data(
            'vertexai-endpoint-location-default', project_id=project_id)
    else:
        session_factory = test.replay_flight_data(
            'vertexai-endpoint-location-default')

    # No query, no config - should use all Vertex AI regions
    policy = test.load_policy({
        'name': 'test-location-default',
        'resource': 'gcp.vertex-ai-endpoint'
    }, session_factory=session_factory)

    resources = policy.run()

    # Should query all Vertex AI regions, so resources could be from any region
    # Just verify that if we have resources, they have the location annotation
    if resources:
        assert all('c7n:location' in r for r in resources)


def test_vertexai_endpoint_monitor_invalid_schema_uri(test):
    """Test monitor action with invalid GCS schema URI validation"""
    policy = test.load_policy({
        'name': 'test-invalid-schema-uri-format',
        'resource': 'gcp.vertex-ai-endpoint',
        'filters': [{'displayName': 'test-endpoint'}],
        'actions': [{
            'type': 'monitor',
            'analysis_instance_schema_uri': 'gs://test-bucket/schema.yaml'
        }]
    })

    action = policy.resource_manager.actions[0]

    # Test 1: Invalid GCS URI format (not starting with gs://)
    try:
        action.validate_schema('https://invalid-url/schema.yaml')
        assert False, 'Should have raised ValueError for non-GCS URI'
    except ValueError as e:
        assert 'must be a GCS path' in str(e)

    # Test 2: Invalid file extension (not .yaml or .yml)
    try:
        action.validate_schema('gs://bucket/schema.json')
        assert False, 'Should have raised ValueError for non-YAML file'
    except ValueError as e:
        assert 'must be YAML format' in str(e)


def test_vertexai_endpoint_monitor_schema_yaml_validation(test):
    """Test monitor action schema YAML parsing and validation

    This test validates the schema validation logic by mocking GCS blob downloads
    to test various invalid schema formats without requiring actual GCS files.
    """
    session_factory = test.replay_flight_data('vertexai-endpoint-monitor')
    bucket_name = 'test-bucket'

    policy = test.load_policy({
        'name': 'test-schema-yaml-validation',
        'resource': 'gcp.vertex-ai-endpoint',
        'filters': [{'displayName': 'test-endpoint'}],
        'actions': [{
            'type': 'monitor',
            'analysis_instance_schema_uri': f'gs://{bucket_name}/schema/instance_schema.yaml'
        }]
    }, session_factory=session_factory)

    action = policy.resource_manager.actions[0]

    # Mock the GCS storage client to return test data
    with patch('c7n_gcp.resources.vertexai.storage.Client') as mock_storage_client:
        mock_client = Mock()
        mock_storage_client.return_value = mock_client
        mock_bucket = Mock()
        mock_blob = Mock()
        mock_bucket.blob.return_value = mock_blob
        mock_client.bucket.return_value = mock_bucket

        # Test 0: Valid schema (success case)
        mock_blob.download_as_text.return_value = (
            'type: object\nproperties:\n  field1:\n    type: string'
        )
        result = action.validate_schema(
            f'gs://{bucket_name}/schema/instance_schema.yaml'
        )
        assert result is True

        # Test 1: Invalid YAML content
        mock_blob.download_as_text.return_value = 'invalid: yaml: content: ['
        try:
            action.validate_schema(f'gs://{bucket_name}/schema/invalid.yaml')
            assert False, 'Should have raised ValueError for invalid YAML'
        except ValueError as e:
            assert 'is not valid YAML' in str(e)

        # Test 2: Schema is not a dict (e.g., a list)
        mock_blob.download_as_text.return_value = '- item1\n- item2'
        try:
            action.validate_schema(f'gs://{bucket_name}/schema/list.yaml')
            assert False, 'Should have raised ValueError for non-dict schema'
        except ValueError as e:
            assert 'Schema must be a YAML object (dict)' in str(e)

        # Test 3: Schema dict missing 'type' field
        mock_blob.download_as_text.return_value = 'properties:\n  field1:\n    type: string'
        try:
            action.validate_schema(f'gs://{bucket_name}/schema/no-type.yaml')
            assert False, 'Should have raised ValueError for missing type field'
        except ValueError as e:
            assert 'Schema must have a "type" field' in str(e)

    # Test 4: No schema URI provided (should return True)
    result = action.validate_schema(None)
    assert result is True


class VertexAIPublisherModelTest(BaseTest):
    """Test Vertex AI Publisher Models resource

    Tests the gcp.vertex-ai-publisher-model resource which provides access
    to the Vertex AI Model Garden catalog of publisher models.

    Note: This resource queries a read-only catalog provided by Google,
    so no terraform infrastructure is needed.

    API Version: Uses v1beta1 because v1 does not support list operations.
    If tests start failing, check if the v1beta1 API has been deprecated
    or if v1 has gained list support (see vertexai.py VertexAIPublisherModel for migration path).
    """

    def test_publisher_resource_query(self):
        """Test listing synthetic Vertex AI publishers from JSON data."""
        policy = self.load_policy(
            {'name': 'vertex-ai-publishers',
             'resource': 'gcp.vertex-ai-publisher'})

        resources = policy.run()

        self.assertGreaterEqual(len(resources), 1)
        for resource in resources:
            self.assertRegex(resource.get('name', ''), r'^publishers/[^/]+$')

    def test_publisher_model_query(self):
        """Test listing Vertex AI publisher models."""

        # Use record_flight_data in functional mode, replay_flight_data otherwise
        if C7N_FUNCTIONAL:
            project_id = get_default_project()
            session_factory = self.record_flight_data(
                'vertex-ai-publisher-model-query', project_id=project_id)
        else:
            session_factory = self.replay_flight_data('vertex-ai-publisher-model-query')

        policy = self.load_policy(
            {'name': 'vertex-ai-publisher-models',
             'resource': 'gcp.vertex-ai-publisher-model'},
            session_factory=session_factory)

        resources = policy.run()

        self.assertGreaterEqual(len(resources), 1)

    def test_publisher_model_filter_by_launch_stage(self):
        """Test filtering publisher models by launch stage."""
        if C7N_FUNCTIONAL:
            project_id = get_default_project()
            session_factory = self.record_flight_data(
                'vertex-ai-publisher-model-filter-launch-stage', project_id=project_id)
        else:
            session_factory = self.replay_flight_data(
                'vertex-ai-publisher-model-filter-launch-stage')

        policy = self.load_policy(
            {'name': 'ga-publisher-models',
             'resource': 'gcp.vertex-ai-publisher-model',
             'filters': [
                 {'type': 'value',
                  'key': 'launchStage',
                  'value': 'GA'}
             ]},
            session_factory=session_factory)

        resources = policy.run()

        # Verify all returned models are GA
        self.assertIsNotNone(resources)
        for resource in resources:
            self.assertEqual(resource.get('launchStage'), 'GA',
                           f'Model {resource.get("name")} is not GA')

    def test_publisher_model_filter_by_name_pattern(self):
        """Test filtering publisher models by name pattern."""
        if C7N_FUNCTIONAL:
            project_id = get_default_project()
            session_factory = self.record_flight_data(
                'vertex-ai-publisher-model-filter-name', project_id=project_id)
        else:
            session_factory = self.replay_flight_data(
                'vertex-ai-publisher-model-filter-name')

        policy = self.load_policy(
            {'name': 'gemini-models',
             'resource': 'gcp.vertex-ai-publisher-model',
             'filters': [
                 {'type': 'value',
                  'key': 'name',
                  'op': 'regex',
                  'value': '.*gemini.*'}
             ]},
            session_factory=session_factory)

        resources = policy.run()

        # Verify all returned models have 'gemini' in the name
        self.assertIsNotNone(resources)
        for resource in resources:
            self.assertIn('gemini', resource.get('name', '').lower(),
                        f'Model {resource.get("name")} does not match pattern')

    def test_publisher_model_field_validation(self):
        """Test that expected fields are present in publisher model resources."""
        if C7N_FUNCTIONAL:
            project_id = get_default_project()
            session_factory = self.record_flight_data(
                'vertex-ai-publisher-model-fields', project_id=project_id)
        else:
            session_factory = self.replay_flight_data(
                'vertex-ai-publisher-model-fields')

        policy = self.load_policy(
            {'name': 'validate-fields',
             'resource': 'gcp.vertex-ai-publisher-model'},
            session_factory=session_factory)

        resources = policy.run()

        self.assertGreater(len(resources), 0, 'Should return at least one model')

        # Validate expected fields are present
        expected_fields = ['name', 'versionId', 'launchStage', 'publisherModelTemplate']
        model = resources[0]

        for field in expected_fields:
            self.assertIn(field, model, f'Missing expected field: {field}')

        # Validate field types
        self.assertIsInstance(model.get('name'), str)
        self.assertIsInstance(model.get('versionId'), str)
        self.assertIsInstance(model.get('launchStage'), str)

    def test_publisher_model_multiple_filters(self):
        """Test combining multiple filters on publisher models."""
        if C7N_FUNCTIONAL:
            project_id = get_default_project()
            session_factory = self.record_flight_data(
                'vertex-ai-publisher-model-multi-filter', project_id=project_id)
        else:
            session_factory = self.replay_flight_data(
                'vertex-ai-publisher-model-multi-filter')

        policy = self.load_policy(
            {'name': 'ga-gemini-models',
             'resource': 'gcp.vertex-ai-publisher-model',
             'filters': [
                 {'type': 'value',
                  'key': 'launchStage',
                  'value': 'GA'},
                 {'type': 'value',
                  'key': 'name',
                  'op': 'regex',
                  'value': '.*gemini.*'}
             ]},
            session_factory=session_factory)

        resources = policy.run()

        # Verify all returned models match both filters
        self.assertIsNotNone(resources)
        for resource in resources:
            self.assertEqual(resource.get('launchStage'), 'GA')
            self.assertIn('gemini', resource.get('name', '').lower())

    def test_publisher_model_non_google_publisher(self):
        """Test filtering for non-Gemini publisher models.

        Note: This test filters the Google publisher results for non-Gemini models.
        The resource currently queries publishers/google, which may include models
        from various publishers in the Google catalog.
        """
        if C7N_FUNCTIONAL:
            project_id = get_default_project()
            session_factory = self.record_flight_data(
                'vertex-ai-publisher-model-non-google', project_id=project_id)
        else:
            session_factory = self.replay_flight_data(
                'vertex-ai-publisher-model-non-google')

        policy = self.load_policy(
            {'name': 'non-gemini-models',
             'resource': 'gcp.vertex-ai-publisher-model',
             'filters': [
                 {'not': [
                     {'type': 'value',
                      'key': 'name',
                      'op': 'regex',
                      'value': '.*gemini.*'}
                 ]}
             ]},
            session_factory=session_factory)

        resources = policy.run()

        self.assertIsNotNone(resources)
        self.assertGreater(
            len(resources), 0, 'Expected at least one non-Gemini publisher model')

        for resource in resources:
            self.assertNotIn(
                'gemini',
                resource.get('name', '').lower(),
                f'Model {resource.get("name")} unexpectedly matched Gemini pattern'
            )
