# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import time

import freezegun
import pytest
from googleapiclient import errors
from pytest_terraform import terraform

from c7n_gcp import client as gcp_client
from c7n_gcp.resources import vertexai


TERMINAL_STATES = {
    'PIPELINE_STATE_SUCCEEDED',
    'PIPELINE_STATE_FAILED',
    'PIPELINE_STATE_CANCELLED',
}


class PipelineJobs:
    def __init__(self, test, pipeline_root: str, service_account: str) -> None:
        self.test = test
        self.pipeline_root = pipeline_root
        self.service_account = service_account
        self.created = []

    def client(self, location: str) -> gcp_client.ServiceClient:
        return vertexai.VertexAIQueryManager.get_location_client(
            self.test.session_factory(),
            location,
            'projects.locations.pipelineJobs',
        )

    def create(self, location: str, display_name: str, command: str) -> dict:
        client = self.client(location)
        project = self.test.session_factory().get_default_project()
        job = client.execute_command(
            'create',
            {
                'parent': f'projects/{project}/locations/{location}',
                'body': {
                    'displayName': display_name,
                    'labels': {'purpose': display_name},
                    'serviceAccount': self.service_account,
                    'runtimeConfig': {'gcsOutputDirectory': self.pipeline_root},
                    'pipelineSpec': {
                        'pipelineInfo': {'name': 'c7n-test-pipeline'},
                        'schemaVersion': '2.1.0',
                        'sdkVersion': 'kfp-2.0.0',
                        'root': {
                            'dag': {
                                'tasks': {
                                    'task': {
                                        'taskInfo': {'name': 'task'},
                                        'componentRef': {'name': 'comp-task'},
                                    },
                                },
                            },
                        },
                        'components': {'comp-task': {'executorLabel': 'exec-task'}},
                        'deploymentSpec': {
                            'executors': {
                                'exec-task': {
                                    'container': {
                                        'image': (
                                            'gcr.io/google.com/'
                                            'cloudsdktool/cloud-sdk:slim'
                                        ),
                                        'command': ['sh', '-c', command],
                                    },
                                },
                            },
                        },
                    },
                },
            },
        )
        self.created.append((client, job['name']))
        return job

    def wait(
        self,
        client: gcp_client.ServiceClient,
        name: str,
        states: set[str],
    ) -> dict:
        for _ in range(90):
            job = client.execute_query('get', {'name': name})
            if job['state'] in states:
                return job
            assert job['state'] not in TERMINAL_STATES, job.get('error', job['state'])
            if self.test.recording:
                time.sleep(10)
        raise AssertionError(f"Pipeline {name} remained in {job['state']}")

    def cleanup(self) -> None:
        for client, name in self.created:
            try:
                job = client.execute_query('get', {'name': name})
            except errors.HttpError as exc:
                if exc.resp.status != 404:
                    raise
                continue
            if job['state'] not in TERMINAL_STATES:
                client.execute_command('cancel', {'name': name})
                self.wait(client, name, TERMINAL_STATES)
            client.execute_command('delete', {'name': name})


@pytest.fixture
def pipeline_jobs(test, vertexai_pipeline_job):
    outputs = vertexai_pipeline_job.outputs
    jobs = PipelineJobs(
        test,
        outputs['pipeline_root']['value'],
        outputs['service_account']['value'],
    )
    try:
        yield jobs
    finally:
        jobs.cleanup()


@terraform('vertexai_pipeline_job')
def test_vertexai_pipeline_job_inventory(test, pipeline_jobs):
    test.session_factory = test.replay_flight_data('vertexai-pipeline-job-inventory')
    first = pipeline_jobs.create('us-central1', 'c7n-pipeline-retain', 'echo hello')
    first = pipeline_jobs.wait(
        pipeline_jobs.client('us-central1'),
        first['name'],
        {'PIPELINE_STATE_SUCCEEDED'},
    )
    second = pipeline_jobs.create('us-east1', 'c7n-pipeline-review', 'echo hello')
    pipeline_jobs.wait(
        pipeline_jobs.client('us-east1'),
        second['name'],
        {'PIPELINE_STATE_SUCCEEDED'},
    )
    policy_data = {
        'name': 'pipeline-inventory',
        'resource': 'gcp.vertex-ai-pipeline-job',
        'query': [{'location': 'us-central1'}, {'location': 'us-east1'}],
        'filters': [
            {
                'type': 'value',
                'key': 'name',
                'op': 'in',
                'value': [first['name'], second['name']],
            },
        ],
    }
    project = test.session_factory().get_default_project()
    policy = test.load_policy(
        policy_data,
        session_factory=test.session_factory,
    )
    resources = policy.run()
    assert {r['name'] for r in resources} == {first['name'], second['name']}
    assert {r['c7n:location']['name'] for r in resources} == {'us-central1', 'us-east1'}
    assert policy.resource_manager.get_resource(
        {'resourceName': first['name']},
    )['name'] == first['name']
    assert set(policy.resource_manager.get_urns(resources)) == {
        f"gcp:aiplatform:us-central1:{project}:pipeline-job/"
        f"{first['name'].split('/')[-1]}",
        f"gcp:aiplatform:us-east1:{project}:pipeline-job/"
        f"{second['name'].split('/')[-1]}",
    }

    end_time = datetime.datetime.fromisoformat(first['endTime'].replace('Z', '+00:00'))
    with freezegun.freeze_time(end_time + datetime.timedelta(days=30, seconds=1)):
        policy_data['filters'].extend(
            [
                {
                    'type': 'value',
                    'key': 'state',
                    'op': 'in',
                    'value': [
                        'PIPELINE_STATE_SUCCEEDED',
                        'PIPELINE_STATE_FAILED',
                        'PIPELINE_STATE_CANCELLED',
                    ],
                },
                {
                    'type': 'value',
                    'key': 'endTime',
                    'value_type': 'age',
                    'op': 'greater-than',
                    'value': 30,
                },
                {
                    'type': 'value',
                    'key': 'createTime',
                    'value_type': 'age',
                    'op': 'less-than',
                    'value': 31,
                },
            ],
        )
        policy = test.load_policy(policy_data, session_factory=test.session_factory)
        assert [r['name'] for r in policy.run()] == [first['name']]

    for key in ['displayName', 'labels.purpose']:
        policy_data['filters'] = [
            {'type': 'value', 'key': key, 'value': 'c7n-pipeline-review'},
        ]
        policy = test.load_policy(policy_data, session_factory=test.session_factory)
        assert [r['name'] for r in policy.run()] == [second['name']]


@terraform('vertexai_pipeline_job')
def test_vertexai_pipeline_job_cancel_delete(test, pipeline_jobs):
    test.session_factory = test.replay_flight_data(
        'vertexai-pipeline-job-cancel-delete',
    )
    job = pipeline_jobs.create('us-central1', 'c7n-pipeline-cancel', 'sleep 600')
    client = pipeline_jobs.client('us-central1')
    pipeline_jobs.wait(client, job['name'], {'PIPELINE_STATE_RUNNING'})
    policy_data = {
        'name': 'pipeline-cancel',
        'resource': 'gcp.vertex-ai-pipeline-job',
        'query': [{'location': 'us-central1'}],
        'filters': [{'name': job['name']}],
        'actions': ['cancel'],
    }
    policy = test.load_policy(policy_data, session_factory=test.session_factory)
    assert [r['name'] for r in policy.run()] == [job['name']]
    cancelled = pipeline_jobs.wait(client, job['name'], TERMINAL_STATES)
    assert cancelled['state'] == 'PIPELINE_STATE_CANCELLED'

    policy_data['actions'] = ['delete']
    policy = test.load_policy(policy_data, session_factory=test.session_factory)
    assert [r['name'] for r in policy.run()] == [job['name']]
    for _ in range(30):
        try:
            client.execute_query('get', {'name': job['name']})
        except errors.HttpError as exc:
            assert exc.resp.status == 404
            break
        if test.recording:
            time.sleep(2)
    else:
        raise AssertionError('Deleted pipeline job still exists')
