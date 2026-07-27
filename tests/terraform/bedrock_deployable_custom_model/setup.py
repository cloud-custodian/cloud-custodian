#!/usr/bin/env python3
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Submit the customization job that builds this fixture's custom model.

Terraform cannot own the resulting custom model: aws_bedrock_custom_model
deletes the model on destroy, and this model is a long-lived fixture that must
survive `tofu destroy` of its transient prerequisites (see README.md). So
main.tf creates only the buckets, training data, and IAM role, and this script
submits the job that produces the model.

This script does not wait for the job. Customization takes hours, nearly all of
it queued waiting for training capacity, so blocking is impractical -- and
credentials tend to expire out from under a long wait. It submits the job and
prints the command to check on it.

All configuration comes from main.tf's outputs, so this file is identical to the
one in the sibling bedrock_provisionable_custom_model fixture. Each fixture
directory is kept self-contained rather than sharing a parameterized script.

Usage, after `tofu apply` in this directory:

    ./setup.py
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

HERE = Path(__file__).parent
IAM_PROPAGATION_TIMEOUT_SECONDS = 300
RETRY_SECONDS = 20


def tofu_outputs():
    result = subprocess.run(
        ['tofu', 'output', '-json'],
        cwd=HERE, check=True, text=True, capture_output=True)
    return {k: v['value'] for k, v in json.loads(result.stdout).items()}


def as_tag_list(tags):
    return [{'key': k, 'value': v} for k, v in sorted(tags.items())]


def is_iam_propagation_error(err):
    """True for the transient failures seen while a fresh role propagates."""
    code = err.response.get('Error', {}).get('Code', '')
    message = err.response.get('Error', {}).get('Message', '').lower()
    if code not in ('ValidationException', 'AccessDeniedException'):
        return False
    return any(token in message for token in (
        'cannot be assumed', 'unable to assume', 'not authorized', 'role'))


def main():
    outputs = tofu_outputs()
    region = outputs['region']
    client = boto3.client('bedrock', region_name=region)

    # Jobs cannot be deleted (there is no DeleteModelCustomizationJob API, only
    # Stop) and job names must be unique, so timestamp each submission. The
    # prefix carries the owner's username so accumulated jobs stay attributable.
    job_name = '{}-{:%Y%m%d%H%M%S}'.format(
        outputs['job_name_prefix'], datetime.now(timezone.utc))

    request = dict(
        jobName=job_name,
        customModelName=outputs['custom_model_name'],
        roleArn=outputs['execution_role_arn'],
        baseModelIdentifier=outputs['base_model_identifier'],
        customizationType='FINE_TUNING',
        trainingDataConfig={'s3Uri': outputs['training_data_s3_uri']},
        outputDataConfig={'s3Uri': outputs['output_s3_uri']},
        hyperParameters=outputs['hyperparameters'],
        # Terraform cannot tag a model it does not create, so tag here. The
        # KEEP tag explains the fixture to anyone cleaning up the account.
        jobTags=as_tag_list(outputs['fixture_tags']),
        customModelTags=as_tag_list(outputs['fixture_tags']),
    )

    deadline = time.monotonic() + IAM_PROPAGATION_TIMEOUT_SECONDS
    while True:
        try:
            job_arn = client.create_model_customization_job(**request)['jobArn']
            break
        except ClientError as err:
            if not is_iam_propagation_error(err) or time.monotonic() >= deadline:
                raise
            print(f'waiting for IAM propagation: {err}')
            time.sleep(RETRY_SECONDS)

    print(f'submitted {job_name}')
    print(f'  {job_arn}')
    print()
    print('This takes hours. Check on it with:')
    print(f'  aws bedrock get-model-customization-job --region {region} \\')
    print(f'    --job-identifier {job_arn} \\')
    print("    --query '{status:status,"
          "training:statusDetails.trainingDetails.status,model:outputModelArn}'")
    print()
    print('Once status is Completed, tear down these prerequisites with '
          '`tofu destroy`;')
    print('the custom model is not managed by Terraform and survives that.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
