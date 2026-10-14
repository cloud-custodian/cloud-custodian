#!/usr/bin/env python3
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Emit token metrics for an application inference profile and await them."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

import boto3

TIMEOUT = 900


def load_profile():
    resources_path = Path(__file__).with_name('tf_resources.json')
    resources = json.loads(resources_path.read_text())
    return resources['resources']['aws_bedrock_inference_profile']['token_metrics']


def find_inference_profile(profile_name, region):
    bedrock = boto3.client('bedrock', region_name=region)
    request = {'typeEquals': 'APPLICATION'}
    while True:
        response = bedrock.list_inference_profiles(**request)
        inference_profile = next((
            p for p in response['inferenceProfileSummaries']
            if p['inferenceProfileName'] == profile_name), None)
        if inference_profile:
            return inference_profile
        if 'nextToken' not in response:
            raise RuntimeError(f'could not find inference profile {profile_name!r}')
        request['nextToken'] = response['nextToken']


def emit_token_metrics(inference_profile_arn, region):
    runtime = boto3.client('bedrock-runtime', region_name=region)
    runtime.converse(
        modelId=inference_profile_arn,
        messages=[{
            'role': 'user',
            'content': [{'text': 'Reply with the single word hello.'}],
        }],
        inferenceConfig={'maxTokens': 8, 'temperature': 0},
    )


def wait_for_token_metrics(inference_profile_id, region):
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        end = datetime.now(timezone.utc)
        available = []
        for metric in ('InputTokenCount', 'OutputTokenCount'):
            response = cloudwatch.get_metric_statistics(
                Namespace='AWS/Bedrock',
                MetricName=metric,
                Dimensions=[{'Name': 'ModelId', 'Value': inference_profile_id}],
                StartTime=end - timedelta(hours=1),
                EndTime=end,
                Period=60,
                Statistics=['Sum'],
            )
            available.append(bool(response['Datapoints']))
        if all(available):
            print('InputTokenCount and OutputTokenCount are available.')
            return
        time.sleep(15)
    raise TimeoutError('timed out waiting for Bedrock token metrics')


def main():
    profile = load_profile()
    inference_profile = find_inference_profile(profile['name'], profile['region'])
    emit_token_metrics(inference_profile['inferenceProfileArn'], profile['region'])
    wait_for_token_metrics(inference_profile['inferenceProfileId'], profile['region'])


if __name__ == '__main__':
    main()
