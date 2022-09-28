# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import unittest
import time

import datetime
from dateutil import tz
import jmespath
from mock import mock

from c7n.testing import mock_datetime_now
from c7n.exceptions import PolicyValidationError, ClientError
from c7n.resources import ec2
from c7n.resources.ec2 import actions, QueryFilter
from c7n import tags, utils

from .common import BaseTest

import pytest
from pytest_terraform import terraform


@terraform('ec2_metadata_tags_enabled')
def test_ec2_metadata_tags_enabled(test, ec2_metadata_tags_enabled):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data('ec2_metadata_tags_enabled', region=aws_region)

    p = test.load_policy(
        {
            'name': 'ec2_metadata_tags_enabled',
            'resource': 'ec2',
            'filters': [
                {
                    'type': 'value',
                    'op': 'in',
                    'key': 'InstanceId',
                    'value': [
                        ec2_metadata_tags_enabled['aws_instance.metadata_tags.id'],
                    ],
                },
                {'MetadataOptions.InstanceMetadataTags': 'enabled'},
                {'type': 'set-metadata-access'},
            ],
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(
        resources[0]['InstanceId'],
        ec2_metadata_tags_enabled['aws_instance.metadata_tags.id'])

    # set the api stop protection to false to allow terraform to handle the teardown
    client = session_factory().client('ec2')
    client.modify_instance_attribute(
        InstanceId=resources[0]['InstanceId'],
        DisableApiStop={'Value': False}
    )


@terraform('ec2_metadata_tags_disabled')
def test_ec2_metadata_tags_disabled(test, ec2_metadata_tags_disabled):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data('ec2_metadata_tags_disabled', region=aws_region)

    p = test.load_policy(
        {
            'name': 'ec2_metadata_tags_disabled',
            'resource': 'ec2',
            'filters': [
                {
                    'type': 'value',
                    'op': 'in',
                    'key': 'InstanceId',
                    'value': [
                        ec2_metadata_tags_disabled['aws_instance.metadata_tags.id'],
                    ],
                },
                {'MetadataOptions.InstanceMetadataTags': 'disabled'},
                {'not': [{'type': 'set-metadata-access'}]},
            ],
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    test.assertEqual(len(resources), 2)

    resource_ids = [i['InstanceId'] for i in resources]
    test.assertIn(
        ec2_metadata_tags_disabled['aws_instance.termination_protection.id'],
        resource_ids)
    test.assertIn(
        ec2_metadata_tags_disabled['aws_instance.no_protection.id'],
        resource_ids)

    # set the api stop protection to false to allow terraform to handle the teardown
    client = session_factory().client('ec2')
    client.modify_instance_attribute(
        InstanceId=ec2_metadata_tags_disabled['aws_instance.metadata_tags.id'],
        DisableApiStop={'Value': False}
    )


class TestSetMetadata(BaseTest):

    def test_set_metadata_server(self):
        output = self.capture_logging('custodian.actions')
        session_factory = self.replay_flight_data('test_ec2_set_md_access')
        policy = self.load_policy({
            'name': 'ec2-imds-access',
            'resource': 'aws.ec2',
            'actions': [
                {'type': 'set-metadata-access',
                 'tokens': 'required'},
            ]},
            session_factory=session_factory)
        resources = policy.run()
        if self.recording:
            time.sleep(2)
        results = session_factory().client('ec2').describe_instances(
            InstanceIds=[r['InstanceId'] for r in resources])
        self.assertJmes('[0].MetadataOptions.HttpTokens', resources, 'optional')
        self.assertJmes(
            'Reservations[].Instances[].MetadataOptions',
            results,
            [{'HttpEndpoint': 'enabled',
              'HttpPutResponseHopLimit': 1,
              'HttpTokens': 'required',
              'InstanceMetadataTags': 'disabled',
              'State': 'pending'},
             {'HttpEndpoint': 'enabled',
              'HttpPutResponseHopLimit': 1,
              'HttpTokens': 'required',
              'InstanceMetadataTags': 'disabled',
              'State': 'applied'}])
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            output.getvalue(),
            ('set-metadata-access implicitly filtered 1 of 2 resources '
             'key:MetadataOptions.HttpTokens on optional\n'))


class TestSetMetadataTags(BaseTest):

    def test_set_metadata_server(self):
        output = self.capture_logging('custodian.actions')
        session_factory = self.replay_flight_data('test_ec2_set_md_access')
        policy = self.load_policy({
            'name': 'ec2-imds-access',
            'resource': 'aws.ec2',
            'actions': [
                {'type': 'set-metadata-access',
                 'metadatatags': 'enabled'},
            ]},
            session_factory=session_factory)
        resources = policy.run()
        if self.recording:
            time.sleep(2)
        results = session_factory().client('ec2').describe_instances(
            InstanceIds=[r['InstanceId'] for r in resources])
        self.assertJmes('[0].MetadataOptions.InstanceMetadataTags', resources, 'disabled')
        self.assertJmes(
            'Reservations[].Instances[].MetadataOptions',
            results,
            [{'HttpEndpoint': 'enabled',
              'HttpPutResponseHopLimit': 1,
              'HttpTokens': 'optional',
              'InstanceMetadataTags': 'enabled',
              'State': 'pending'},
             {'HttpEndpoint': 'enabled',
              'HttpPutResponseHopLimit': 1,
              'HttpTokens': 'optional',
              'InstanceMetadataTags': 'enabled',
              'State': 'applied'}])
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            output.getvalue(),
            ('set-metadata-access implicitly filtered 1 of 2 resources '
             'key:MetadataOptions.InstanceMetadataTags on disabled\n'))


