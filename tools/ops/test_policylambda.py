# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import jmespath

from c7n.config import Config
from c7n.loader import PolicyLoader
from policylambda import dispatch_render


def test_config_rule_policy():
    collection = PolicyLoader(Config.empty()).load_data(
        {'policies': [{
            'name': 'check-ec2',
            'resource': 'ec2',
            'mode': {
                'type': 'config-rule'}}]},
        file_uri=":mem:")
    sam = {'Resources': {}}
    p = list(collection).pop()
    dispatch_render(p, sam)
    assert set(sam['Resources']) == set((
        'CheckEc2', 'CheckEc2ConfigRule', 'CheckEc2InvokePermission'))
    assert jmespath.search(
        'Resources.CheckEc2ConfigRule.Properties.Source.SourceIdentifier',
        sam) == {'Fn::GetAtt': 'CheckEc2' + '.Arn'}


def test_cloudtrail_policy():
    collection = PolicyLoader(Config.empty()).load_data(
        {'policies': [{
            'name': 'check-ec2',
            'resource': 'ec2',
            'mode': {
                'type': 'cloudtrail',
                'events': ['RunInstances']}}]},
        file_uri=":mem:")
    sam = {'Resources': {}}
    p = list(collection).pop()
    dispatch_render(p, sam)
    assert sam['Resources']['CheckEc2']['Properties']['Events'] == {
        'PolicyTriggerA': {
            'Properties': {
                'Pattern': {
                    'detail': {
                        'eventName': ['RunInstances'],
                        'eventSource': ['ec2.amazonaws.com']},
                    'detail-type': [
                        'AWS API Call via CloudTrail']}},
            'Type': 'CloudWatchEvent'}
    }


def test_periodic_policy():
    collection = PolicyLoader(Config.empty()).load_data(
        {'policies': [{
            'name': 'check-ec2',
            'resource': 'ec2',
            'mode': {
                'schedule': 'rate(1 hour)',
                'type': 'periodic'}}]},
        file_uri=":mem:")
    sam = {'Resources': {}}
    p = list(collection).pop()
    dispatch_render(p, sam)
    assert sam['Resources']['CheckEc2']['Properties']['Events'] == {
        'PolicySchedule': {
            'Type': 'Schedule',
            'Properties': {
                'Schedule': 'rate(1 hour)'
            }
        }
    }
