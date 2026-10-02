#!/usr/bin/env python3
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Search one knowledge base with each search API and wait for CloudTrail to log it.

A new trail drops events for a while after it starts logging, so the canary
knowledge base is searched until one of those searches reaches the log group.
"""

import json
from pathlib import Path
import time

import boto3

GENERATION_MODEL_ARN = 'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0'
QUERY = 'What does this knowledge base contain?'
POLL_DELAY = 60
TIMEOUT = 1800
# One event per search call, plus the Retrieve that Bedrock runs for the caller
# inside each RetrieveAndGenerate and RetrieveAndGenerateStream call.
EXPECTED_EVENTS = 5


def load_fixture():
    resources_path = Path(__file__).with_name('tf_resources.json')
    resources = json.loads(resources_path.read_text())['resources']
    knowledge_bases = resources['aws_bedrockagent_knowledge_base']
    log_group = resources['aws_cloudwatch_log_group']['trail']
    return knowledge_bases['canary'], knowledge_bases['used'], log_group


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
    canary, used, log_group = load_fixture()
    runtime = boto3.client('bedrock-agent-runtime', region_name=used['region'])
    logs = boto3.client('logs', region_name=log_group['region'])
    wait_for_trail(runtime, logs, log_group['name'], canary['id'])
    search_knowledge_base(runtime, used['id'])
    wait_for_events(logs, log_group['name'], used['id'])


if __name__ == '__main__':
    main()
