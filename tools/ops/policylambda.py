#!/usr/bin/env python3
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
$ aws cloudformation package --template-file deploy.yml \
      --s3-bucket mybucket --output-template-file cfn.yml
$ aws cloudformation deploy cfn.yml
```

"""
import argparse
import json
import os
import string
import yaml

from c7n.config import Config
from c7n.loader import PolicyLoader
from c7n import mu


def render_function_properties(p, policy_lambda):
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

    return properties


def render_periodic(p, policy_lambda, sam):
    properties = render_function_properties(p, policy_lambda)
    revents = {
        'PolicySchedule': {
            'Type': 'Schedule',
            'Properties': {
                'Schedule': p.data.get('mode', {}).get('schedule')}}
    }
    properties['Events'] = revents
    return properties


def render_cwe(p, policy_lambda, sam):
    properties = render_function_properties(p, policy_lambda)

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
    return properties


def render_config_rule(p, policy_lambda, sam):
    properties = render_function_properties(p, policy_lambda)
    policy_lambda.arn = {'Fn::GetAtt': resource_name(p.name) + ".Arn"}
    config_rule = policy_lambda.get_events(None).pop()
    rule_properties = config_rule.get_rule_params(policy_lambda)

    if p.execution_mode == 'config-poll-rule':
        rule_properties.pop('Scope', None)

    sam['Resources'][resource_name(p.name) + 'ConfigRule'] = {
        'Type': 'AWS::Config::ConfigRule',
        'DependsOn': resource_name(p.name) + "InvokePermission",
        'Properties': rule_properties
    }
    sam['Resources'][resource_name(p.name) + 'InvokePermission'] = {
        "DependsOn": resource_name(p.name),
        "Type": "AWS::Lambda::Permission",
        "Properties": {
            "Action": "lambda:InvokeFunction",
            "FunctionName": {"Ref": resource_name(p.name)},
            "Principal": "config.amazonaws.com"
        }
    }
    return properties


SAM_RENDER_FUNCS = {
    'poll': None,
    'periodic': render_periodic,
    'config-rule': render_config_rule,
    'config-poll-rule': render_config_rule,
    'cloudtrail': render_cwe,
    'phd': render_cwe,
    'ec2-instance-state': render_cwe,
    'asg-instance-state': render_cwe,
    'guard-duty': render_cwe
}


def dispatch_render(p, sam):
    if p.execution_mode not in SAM_RENDER_FUNCS:
        raise ValueError("Unsupported sam deploy mode (%s) on policy: %s" % (
            p.execution_mode, p.name))
    render_func = SAM_RENDER_FUNCS[p.execution_mode]
    if render_func is None:
        return None
    policy_lambda = mu.PolicyLambda(p)
    properties = render_func(p, policy_lambda, sam)
    if properties['Role'].startswith('arn:') and "{account_id}" in properties['Role']:
        properties['Role'] = {'Fn::Sub': properties['Role'].replace("{account_id}", "${AWS::AccountId}")}  # noqa: E501
    elif properties['Role'].startswith('arn:'):
        pass
    else:
        properties['Role'] = {'Fn::Sub': "arn:aws:iam::${AWS::AccountId}:role/%s" % policy_lambda.role}  # noqa: E501
    properties['CodeUri'] = "./%s.zip" % p.name
    sam['Resources'][resource_name(p.name)] = {
        'Type': 'AWS::Serverless::Function',
        'Properties': properties}
    return policy_lambda


def resource_name(policy_name):
    parts = policy_name.replace('_', '-').split('-')
    return "".join(
        [p.title() for p in parts])


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
    collection = PolicyLoader(
        Config.empty()).load_file(options.config_file).filter(options.policy_filter)

    sam = {
        'AWSTemplateFormatVersion': '2010-09-09',
        'Transform': 'AWS::Serverless-2016-10-31',
        'Resources': {}}

    for p in collection:
        if p.provider_name != 'aws':
            continue
        policy_lambda = dispatch_render(p, sam)
        archive = policy_lambda.get_archive()
        with open(os.path.join(options.output_dir, "%s.zip" % p.name), 'wb') as fh:
            fh.write(archive.get_bytes())

    with open(os.path.join(options.output_dir, 'deploy.yml'), 'w') as fh:
        fh.write(yaml.safe_dump(sam, default_flow_style=False))


if __name__ == '__main__':
    main()
