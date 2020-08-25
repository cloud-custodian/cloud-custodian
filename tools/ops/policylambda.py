#!/usr/bin/env python3
# Copyright 2018-2019 Capital One Services, LLC
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Cli tool to package up custodian lambda policies for folks that
want to deploy with different tooling instead of custodian builtin
capabilities.

This will output a set of zip files and a SAM cloudformation template.
that deploys a set of custodian policies.

Usage:

```shell

$ mkdir sam-deploy
$ python policylambda.py -o sam-deploy -c policies.yml

$ cd sam-deploy
$ aws cloudformation --template-file deploy.yml --s3-bucket mybucket > cfn.yml
$ aws cloudformation deploy cfn.yml
```

"""
import argparse
import json
import os
import string
import yaml
import boto3
from boto3.session import Session

from c7n.config import Config
from c7n.policy import load as policy_load
from c7n import mu, resources


def render(p):
    policy_lambda = mu.PolicyLambda(p)
    properties = policy_lambda.get_config()

    # Translate api call params to sam
    env = properties.pop('Environment', None)
    if env and 'Variables' in env:
        properties['Environment'] = env.get('Variables')
    trace = properties.pop('TracingConfig', None)
    if trace:
        properties['Tracing'] = trace.get('Mode', 'PassThrough')
    dlq = properties.pop('DeadLetterConfig', None)
    if dlq:
        properties['DeadLetterQueue'] = {
            'Type': ':sns:' in dlq['TargetArn'] and 'SNS' or 'SQS',
            'TargetArn': dlq['TargetArn']}
    key_arn = properties.pop('KMSKeyArn')
    if key_arn:
        properties['KmsKeyArn']

    if p.execution_mode == 'periodic':
        # Event render
        revents = {}
        revents = {
            'PolicySchedule': {
                'Type': 'Schedule',
                'Properties': {
                    'Schedule': p.data.get('mode', {}).get('schedule')}}
        }
        properties['Events'] = revents

    elif p.execution_mode == 'cloudtrail':
        events = [e for e in policy_lambda.get_events(None)
                if isinstance(e, mu.CloudWatchEventSource)]
        if not events:
            return

        revents = {}
        for idx, e in enumerate(events):
            revents[
                'PolicyTrigger%s' % string.ascii_uppercase[idx]] = {
                    'Type': 'CloudWatchEvent',
                    'Properties': {
                        'Pattern': json.loads(e.render_event_pattern())}
            }
        properties['Events'] = revents

    elif p.execution_mode == 'config-rule':
        properties.pop('Delay', None)

    return {
        'Type': 'AWS::Serverless::Function',
        'Properties': properties}


def render_config_rule(p):
    policy_lambda = mu.PolicyLambda(p)
    policy_lambda.arn = get_lambda_arn(policy_lambda.name)
    config_rule = policy_lambda.get_events(Session)

    properties = config_rule[0].get_rule_params(policy_lambda)

    exec_mode_type = p.data.get('mode', {'type': 'pull'}).get('type')
    if exec_mode_type == 'config-poll-rule':
        properties.pop('Scope', None)

    attributes = {}
    attributes['Type'] = 'AWS::Config::ConfigRule'
    attributes['DependsOn'] = resource_name(p.name) + "Invoke"
    attributes['Properties'] = properties
    return attributes


def render_invoke(name):
    return {
        "DependsOn": name,
        "Type": "AWS::Lambda::Permission",
        "Properties": {
            "Action": "lambda:InvokeFunction",
            "FunctionName": {"Ref": name},
            "Principal": "config.amazonaws.com"
        }
    }


def get_lambda_arn(function_name):
    sts = boto3.client("sts")
    account_id = sts.get_caller_identity()["Arn"].split(":")[4]
    region = boto3.session.Session().region_name
    arn = "arn:aws:lambda:" + str(region) \
          + ":" + account_id + ":function:" \
          + function_name
    return arn


def resource_name(policy_name):
    parts = policy_name.replace('_', '-').split('-')
    return "".join(
        [p.title() for p in parts])


def load_policies(options):
    policies = []
    for f in options.config_files:
        collection = policy_load(options, f)
        policies.extend(collection.filter(options.policy_filter))
    return policies


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c', '--config', dest="config_file", required=True,
        help="Policy configuration files")
    parser.add_argument("-p", "--policies", default=None, dest='policy_filter',
                        help="Only use named/matched policies")
    parser.add_argument("-o", "--output-dir", default=None, required=True)
    return parser


def main():
    parser = setup_parser()
    options = parser.parse_args()
    config = Config.empty()
    resources.load_resources()

    collection = policy_load(
        config, options.config_file).filter(options.policy_filter)

    sam = {
        'AWSTemplateFormatVersion': '2010-09-09',
        'Transform': 'AWS::Serverless-2016-10-31',
        'Resources': {}}

    for p in collection:
        if p.provider_name != 'aws':
            continue
        exec_mode_type = p.data.get('mode', {'type': 'pull'}).get('type')
        if exec_mode_type == 'pull':
            continue

        sam_func = render(p)
        if sam_func:
            sam['Resources'][resource_name(p.name)] = sam_func

            if exec_mode_type == 'config-rule' or exec_mode_type == 'config-poll-rule':
                configrule_resource = render_config_rule(p)
                invoke_resource = render_invoke(resource_name(p.name))
                sam['Resources'][resource_name(p.name) + "Invoke"] = invoke_resource
                sam['Resources'][resource_name(p.name) + "ConfigRule"] = configrule_resource

            sam_func['Properties']['CodeUri'] = './%s.zip' % p.name
        else:
            print("unable to render sam for policy:%s" % p.name)
            continue

        archive = mu.PolicyLambda(p).get_archive()
        with open(os.path.join(options.output_dir, "%s.zip" % p.name), 'wb') as fh:
            fh.write(archive.get_bytes())

    with open(os.path.join(options.output_dir, 'deploy.yml'), 'w') as fh:
        fh.write(yaml.safe_dump(sam, default_flow_style=False))


if __name__ == '__main__':
    main()
