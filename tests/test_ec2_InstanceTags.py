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


@terraform('ec2_stop_protection_enabled')
def test_ec2_stop_protection_enabled(test, ec2_stop_protection_enabled):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data('ec2_stop_protection_enabled', region=aws_region)

    p = test.load_policy(
        {
            'name': 'ec2_stop_protection_enabled',
            'resource': 'ec2',
            'filters': [
                {
                    'type': 'value',
                    'op': 'in',
                    'key': 'InstanceId',
                    'value': [
                        ec2_stop_protection_enabled['aws_instance.termination_protection.id'],
                        ec2_stop_protection_enabled['aws_instance.no_protection.id'],
                        ec2_stop_protection_enabled['aws_instance.stop_protection.id'],
                    ],
                },
                {'State.Name': 'running'},
                {'type': 'stop-protected'},
            ],
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(
        resources[0]['InstanceId'],
        ec2_stop_protection_enabled['aws_instance.stop_protection.id'])

    # set the api stop protection to false to allow terraform to handle the teardown
    client = session_factory().client('ec2')
    client.modify_instance_attribute(
        InstanceId=resources[0]['InstanceId'],
        DisableApiStop={'Value': False}
    )


@terraform('ec2_stop_protection_disabled')
def test_ec2_stop_protection_disabled(test, ec2_stop_protection_disabled):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data('ec2_stop_protection_disabled', region=aws_region)

    p = test.load_policy(
        {
            'name': 'ec2_stop_protection_disabled',
            'resource': 'ec2',
            'filters': [
                {
                    'type': 'value',
                    'op': 'in',
                    'key': 'InstanceId',
                    'value': [
                        ec2_stop_protection_disabled['aws_instance.termination_protection.id'],
                        ec2_stop_protection_disabled['aws_instance.no_protection.id'],
                        ec2_stop_protection_disabled['aws_instance.stop_protection.id'],
                    ],
                },
                {'State.Name': 'running'},
                {'not': [{'type': 'stop-protected'}]},
            ],
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()
    test.assertEqual(len(resources), 2)

    resource_ids = [i['InstanceId'] for i in resources]
    test.assertIn(
        ec2_stop_protection_disabled['aws_instance.termination_protection.id'],
        resource_ids)
    test.assertIn(
        ec2_stop_protection_disabled['aws_instance.no_protection.id'],
        resource_ids)

    # set the api stop protection to false to allow terraform to handle the teardown
    client = session_factory().client('ec2')
    client.modify_instance_attribute(
        InstanceId=ec2_stop_protection_disabled['aws_instance.stop_protection.id'],
        DisableApiStop={'Value': False}
    )


def test_ec2_stop_protection_filter_permissions(test):
    policy = test.load_policy(
        {
            'name': 'ec2-stop-protection',
            'resource': 'ec2',
            'filters': [{'type': 'stop-protected'}],
        },
    )
    permissions = policy.get_permissions()
    test.assertEqual(
        permissions,
        {
            'ec2:DescribeInstances',
            'ec2:DescribeTags',
            'ec2:DescribeInstanceAttribute',
        },
    )


@pytest.mark.parametrize(
    'botocore_version',
    ['1.26.6', '1.25.8', '0.27.27']
)
def test_ec2_stop_protection_lower_botocore_version_validation(test, botocore_version):
    with mock.patch('botocore.__version__', botocore_version):
        with test.assertRaises(PolicyValidationError) as cm:
            policy = test.load_policy(
                {
                    'name': 'ec2-stop-protection',
                    'resource': 'ec2',
                    'filters': [{'type': 'stop-protected'}],
                },
            )
            policy.validate()
        test.assertIn('requires botocore version 1.26.7 or above', str(cm.exception))


@pytest.mark.parametrize(
    'botocore_version',
    ['1.26.7', '1.26.8', '1.27.0', '2.0.0']
)
def test_ec2_stop_protection_above_botocore_version_validation(test, botocore_version):
    with mock.patch('botocore.__version__', botocore_version):
        policy = test.load_policy(
            {
                'name': 'ec2-stop-protection',
                'resource': 'ec2',
                'filters': [{'type': 'stop-protected'}],
            },
        )
        policy.validate()


class TestEc2NetworkLocation(BaseTest):
    def test_ec2_network_location_terminated(self):
        factory = self.replay_flight_data("test_ec2_network_location")
        client = factory().client('ec2')
        resp = client.describe_instances()

        self.assertTrue(len(resp['Reservations'][0]['Instances']), 1)
        self.assertTrue(
            len(resp['Reservations'][0]['Instances'][0]['State']['Name']),
            'terminated'
        )

        policy = self.load_policy(
            {
                'name': 'ec2-network-location',
                'resource': 'ec2',
                'filters': [
                    {'State.Name': 'terminated'},
                    {'type': 'network-location',
                     "key": "tag:some-value"}
                ]
            },
            session_factory=factory
        )
        resources = policy.run()
        self.assertEqual(len(resources), 0)


class TestTagAugmentation(BaseTest):

    def test_tag_augment_empty(self):
        session_factory = self.replay_flight_data("test_ec2_augment_tag_empty")
        # recording was modified to be sans tags
        policy = self.load_policy(
            {"name": "ec2-tags", "resource": "ec2"}, session_factory=session_factory
        )
        resources = policy.run()
        self.assertEqual(len(resources), 0)

    def test_tag_augment(self):
        session_factory = self.replay_flight_data("test_ec2_augment_tags")
        # recording was modified to be sans tags
        policy = self.load_policy(
            {
                "name": "ec2-tags",
                "resource": "ec2",
                "filters": [{"tag:Env": "Production"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestInstanceAttrFilter(BaseTest):

    def test_attr_filter(self):
        session_factory = self.replay_flight_data("test_ec2_instance_attribute")
        policy = self.load_policy(
            {
                "name": "ec2-attr",
                "resource": "ec2",
                "filters": [
                    {
                        "type": "instance-attribute",
                        "attribute": "rootDeviceName",
                        "key": "Value",
                        "value": "/dev/sda1",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(
            resources[0]["c7n:attribute-rootDeviceName"], {"Value": "/dev/sda1"}
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



class TestStart(BaseTest):

    def test_invalid_state_extract(self):
        self.assertEqual(
            ec2.extract_instance_id(
                ("An error occurred (IncorrectInstanceState) when calling "
                 "the StartInstances operation: The instance 'i-abc123' is "
                 "not in a state from which it can be started.")),
            'i-abc123')
        self.assertRaises(
            ValueError,
            ec2.extract_instance_id,
            ("An error occurred (IncorrectInstanceState) when calling "
             "the StartInstances operation: The instance is "
             "not in a state from which it can be started."))

    def test_ec2_start_handle_invalid_state(self):
        policy = self.load_policy({
            "name": "ec2-test-start",
            "resource": "ec2",
            "filters": [],
            "actions": [{"type": "start"}],
        })

        client = mock.MagicMock()
        client.start_instances.side_effect = ClientError(
            {'Error': {
                'Code': 'IncorrectInstanceState',
                'Message': "The instance 'i-08270b9cfb568a1c4' is not in a state from which it can be started" # NOQA
            }}, 'StartInstances')

        start_action = policy.resource_manager.actions[0]
        self.assertEqual(
            start_action.process_instance_set(
                client, [{'InstanceId': 'i-08270b9cfb568a1c4'}], 'm5.xlarge', 'us-east-1a'),
            None)

        client2 = mock.MagicMock()
        client2.start_instances.side_effect = ValueError
        self.assertRaises(
            ValueError,
            start_action.process_instance_set,
            client2, [{'InstanceId': 'i-08270b9cfb568a1c4'}], 'm5.xlarge', 'us-east-1a')

    def test_ec2_start(self):
        session_factory = self.replay_flight_data("test_ec2_start")
        policy = self.load_policy(
            {
                "name": "ec2-test-start",
                "resource": "ec2",
                "filters": [],
                "actions": [{"type": "start"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 2)

    def test_ec2_start_fails(self):
        session_factory = self.replay_flight_data("test_ec2_start")
        policy = self.load_policy(
            {
                "name": "ec2-test-start",
                "resource": "ec2",
                "filters": [],
                "actions": [{"type": "start"}],
            },
            session_factory=session_factory,
        )
        output = self.capture_logging("custodian.actions", level=logging.DEBUG)
        with mock.patch.object(ec2.Start, "process_instance_set", return_value=True):
            try:
                policy.run()
            except RuntimeError:
                pass
            else:
                self.fail("should have raised error")

        log_output = output.getvalue()
        self.assertIn("Could not start 1 of 1 instances", log_output)
        self.assertIn("t2.micro us-west-2c", log_output)
        self.assertIn("i-08270b9cfb568a1c4", log_output)


