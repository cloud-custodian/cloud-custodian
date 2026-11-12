#!/usr/bin/env python3
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Search one knowledge base with each search API and wait for CloudTrail to log it.

A new trail drops events for a while after it starts logging, so the canary
knowledge base is searched until one of those searches reaches the log group.
The filter rejects a window that starts before the trail did, so the searches
wait until the trail is older than the tests' window.
"""

import json
from pathlib import Path
import time

import boto3

GENERATION_MODEL_ARN = 'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0'
QUERY = 'What does this knowledge base contain?'
POLL_DELAY = 60
TIMEOUT = 1800
# RECORDING_WINDOW_DAYS in tests/test_bedrock.py, in seconds.
WINDOW = 1800
# One event per search call, plus the Retrieve that Bedrock runs for the caller
# inside each RetrieveAndGenerate and RetrieveAndGenerateStream call.
EXPECTED_EVENTS = 5


def load_fixture():
    resources_path = Path(__file__).with_name('tf_resources.json')
    resources = json.loads(resources_path.read_text())['resources']
    knowledge_bases = resources['aws_bedrockagent_knowledge_base']
    log_group = resources['aws_cloudwatch_log_group']['trail']
    trail = resources['aws_cloudtrail']['trail']
    return knowledge_bases['canary'], knowledge_bases['used'], log_group, trail


def find_events(logs, log_group_name, knowledge_base_id):
    events = []
    paginator = logs.get_paginator('filter_log_events')
    for page in paginator.paginate(
            logGroupName=log_group_name,
            filterPattern='{ $.eventSource = "bedrock.amazonaws.com" }'):
        for event in page['events']:
            if knowledge_base_id in event['message']:
                events.append(json.loads(event['message']))
    return events


def wait_for_trail(runtime, logs, log_group_name, canary_id):
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        runtime.retrieve(knowledgeBaseId=canary_id, retrievalQuery={'text': QUERY})
        time.sleep(POLL_DELAY)
        if find_events(logs, log_group_name, canary_id):
            print('The trail is logging knowledge base searches.')
            return
    raise TimeoutError(f'no canary search reached the log group after {TIMEOUT}s')


def wait_for_window(cloudtrail, trail_name):
    started = cloudtrail.get_trail_status(Name=trail_name)['StartLoggingTime']
    remaining = started.timestamp() + WINDOW - time.time()
    if remaining > 0:
        print(f'Waiting {remaining / 60:.0f} minutes until the trail is older than the window.')
        time.sleep(remaining)


def search_knowledge_base(runtime, knowledge_base_id):
    runtime.retrieve(knowledgeBaseId=knowledge_base_id, retrievalQuery={'text': QUERY})
    config = {
        'type': 'KNOWLEDGE_BASE',
        'knowledgeBaseConfiguration': {
            'knowledgeBaseId': knowledge_base_id,
            'modelArn': GENERATION_MODEL_ARN,
        },
    }
    runtime.retrieve_and_generate(
        input={'text': QUERY}, retrieveAndGenerateConfiguration=config)
    response = runtime.retrieve_and_generate_stream(
        input={'text': QUERY}, retrieveAndGenerateConfiguration=config)
    for _ in response['stream']:
        pass


def wait_for_events(logs, log_group_name, knowledge_base_id):
    deadline = time.monotonic() + TIMEOUT
    while True:
        events = find_events(logs, log_group_name, knowledge_base_id)
        if len(events) >= EXPECTED_EVENTS or time.monotonic() > deadline:
            break
        time.sleep(POLL_DELAY)
    for event in events:
        print(event['eventName'], 'invoked by', event['userIdentity'].get('invokedBy', 'caller'))
    if len(events) < EXPECTED_EVENTS:
        raise TimeoutError(f'saw {len(events)} of {EXPECTED_EVENTS} events after {TIMEOUT}s')


def main():
    canary, used, log_group, trail = load_fixture()
    runtime = boto3.client('bedrock-agent-runtime', region_name=used['region'])
    logs = boto3.client('logs', region_name=log_group['region'])
    cloudtrail = boto3.client('cloudtrail', region_name=trail['region'])
    wait_for_trail(runtime, logs, log_group['name'], canary['id'])
    wait_for_window(cloudtrail, trail['name'])
    searched = time.time()
    search_knowledge_base(runtime, used['id'])
    # The warm-up searches may fall outside the window by the time the tests run.
    runtime.retrieve(knowledgeBaseId=canary['id'], retrievalQuery={'text': QUERY})
    wait_for_events(logs, log_group['name'], used['id'])
    minutes = (searched + WINDOW - time.time()) / 60
    print(f'Continue the tests within {minutes:.0f} minutes, while the searches are in the window.')


if __name__ == '__main__':
    main()
