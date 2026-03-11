# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os
import json
import time
from google.api_core.client_options import ClientOptions

from c7n.testing import C7N_FUNCTIONAL
from c7n_gcp.client import get_default_project
from c7n.config import Config


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
    print(f'Using model: {full_path} ({location})')
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
