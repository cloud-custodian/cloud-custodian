#!/usr/bin/env python3
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
"""
Script to delete old Vertex AI Batch Prediction Jobs.
This helps clean up test jobs that may interfere with functional tests.

Usage:
    python cleanup_batch_jobs.py [--project PROJECT_ID] [--pattern PATTERN]
"""

import logging
import time

import click
from google.api_core.client_options import ClientOptions
from google.auth import default
from googleapiclient import discovery

log = logging.getLogger('c7n_gcp.cleanup')

# Configuration
LOCATIONS = ['us-central1', 'us-east1']
DEFAULT_PATTERN = 'c7n-test'


def get_credentials_and_project(project_id=None):
    """Get credentials and project ID."""
    credentials, default_project = default()
    project = project_id or default_project
    return credentials, project


def list_batch_jobs(credentials, project_id, location):
    """List all batch prediction jobs in a location."""
    client_options = ClientOptions(
        api_endpoint=f'https://{location}-aiplatform.googleapis.com'
    )

    service = discovery.build(
        'aiplatform', 'v1',
        credentials=credentials,
        client_options=client_options
    )

    parent = f'projects/{project_id}/locations/{location}'

    try:
        request = service.projects().locations().batchPredictionJobs().list(
            parent=parent
        )
        response = request.execute()
        return response.get('batchPredictionJobs', [])
    except Exception as e:
        log.error(f'  Error listing jobs: {e}')
        return []


def cancel_job(credentials, job_name, location):
    """Cancel a running batch prediction job."""
    client_options = ClientOptions(
        api_endpoint=f'https://{location}-aiplatform.googleapis.com'
    )

    service = discovery.build(
        'aiplatform', 'v1',
        credentials=credentials,
        client_options=client_options
    )

    try:
        request = service.projects().locations().batchPredictionJobs().cancel(
            name=job_name
        )
        request.execute()
        return True
    except Exception as e:
        log.error(f'    Failed to cancel: {e}')
        return False


def delete_job(credentials, job_name, location):
    """Delete a batch prediction job."""
    client_options = ClientOptions(
        api_endpoint=f'https://{location}-aiplatform.googleapis.com'
    )

    service = discovery.build(
        'aiplatform', 'v1',
        credentials=credentials,
        client_options=client_options
    )

    try:
        request = service.projects().locations().batchPredictionJobs().delete(
            name=job_name
        )
        request.execute()
        return True
    except Exception as e:
        log.error(f'    Failed to delete: {e}')
        return False


def cleanup_location(credentials, project_id, location, pattern):
    """Clean up jobs in a specific location."""
    log.info(f'Processing location: {location}')

    jobs = list_batch_jobs(credentials, project_id, location)

    if not jobs:
        log.info('  No jobs found')
        return

    deleted_count = 0

    for job in jobs:
        display_name = job.get('displayName', '')
        job_name = job.get('name', '')
        state = job.get('state', '')

        # Check if display name matches our test pattern
        if pattern in display_name:
            log.info(f'  Found test job: {display_name} (state: {state})')

            # Cancel job if it's running or pending
            if state in ['JOB_STATE_RUNNING', 'JOB_STATE_PENDING', 'JOB_STATE_CANCELLING']:
                log.info('    Cancelling job...')
                cancel_job(credentials, job_name, location)
                # Wait for cancellation to complete
                time.sleep(10)

            # Delete the job
            log.info('    Deleting job...')
            if delete_job(credentials, job_name, location):
                deleted_count += 1
                log.info('    ✓ Deleted')
            else:
                log.warning('    ✗ Failed to delete')

    log.info(f'  Deleted {deleted_count} job(s) in {location}')


@click.command()
@click.option(
    '--project',
    help='GCP Project ID (default: from gcloud config)',
    default=None
)
@click.option(
    '--pattern',
    default=DEFAULT_PATTERN,
    help=f'Display name pattern to match (default: {DEFAULT_PATTERN})'
)
def main(project, pattern):
    """Clean up Vertex AI Batch Prediction Jobs."""
    logging.basicConfig(level=logging.INFO)

    credentials, project_id = get_credentials_and_project(project)

    log.info('=== Cleaning up Vertex AI Batch Prediction Jobs ===')
    log.info(f'Project: {project_id}')
    log.info(f'Locations: {LOCATIONS}')
    log.info(f'Display name pattern: {pattern}')
    log.info('')

    for location in LOCATIONS:
        cleanup_location(credentials, project_id, location, pattern)
        log.info('')

    log.info('=== Cleanup complete ===')


if __name__ == '__main__':
    main()
