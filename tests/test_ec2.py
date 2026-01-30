# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import unittest
from unittest import mock
import time

import datetime
from dateutil import tz


from c7n.testing import mock_datetime_now
from c7n.exceptions import PolicyValidationError, ClientError
from c7n.resources import ec2
from c7n.resources.ec2 import actions, EC2QueryParser
from c7n import tags, utils

from .common import BaseTest

import pytest
from pytest_terraform import terraform


# this one doesn't work as a functional test as it enables stop protection, which prevents
# the terraform teardown, we would need to also remove the stop protection in the test.
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


@pytest.mark.audited
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

        self.assertEqual(len(resp['Reservations'][0]['Instances']), 1)
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
        session_factory = self.replay_flight_data('test_ec2_set_md_access')
        policy = self.load_policy({
            'name': 'ec2-imds-access',
            'resource': 'aws.ec2',
            'filters': [{
                    'type': 'value',
                    'key': 'InstanceId',
                    'value': 'i-0d4526dcaa95692db',
                    'op': 'eq'}],
            'actions': [
                {'type': 'set-metadata-access',
                 'tokens': 'required',
                 'metadata-tags': 'enabled'},
            ]},
            session_factory=session_factory)
        resources = policy.run()
        if self.recording:
            time.sleep(10)
        results = session_factory().client('ec2').describe_instances(
            InstanceIds=[r['InstanceId'] for r in resources])
        self.assertJmes('[0].MetadataOptions.InstanceMetadataTags', resources, 'disabled')
        self.assertJmes('Reservations[].Instances[].MetadataOptions', results,
            [{'State': 'applied',
              'HttpTokens': 'required',
              'HttpEndpoint': 'enabled',
              'HttpPutResponseHopLimit': 1,
              'HttpProtocolIpv6': 'disabled',
              'InstanceMetadataTags': 'enabled'}])
        self.assertEqual(len(resources), 1)


class TestMetricFilter(BaseTest):

    def test_metric_filter(self):
        session_factory = self.replay_flight_data("test_ec2_metric")
        policy = self.load_policy(
            {
                "name": "ec2-utilization",
                "resource": "ec2",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "CPUUtilization",
                        "days": 3,
                        "value": 1.5,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_metric_filter_extended_stats(self):
        session_factory = self.replay_flight_data(
            "test_ec2_metric_extended_stats",
            region="us-east-2"
        )
        policy = self.load_policy(
            {
                "name": "ec2-utilization-p95",
                "resource": "aws.ec2",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "CPUUtilization",
                        "days": 7,
                        "value": 10,
                        "op": "less-than",
                        "statistics": "p95",
                    }
                ],
            },
            session_factory=session_factory,
            config={"region": "us-east-2"},
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_metric_filter_multiple_datapoints(self):
        session_factory = self.replay_flight_data("test_metric_filter_multiple_datapoints")
        policy = self.load_policy(
            {
                "name": "ec2-utilization-per-day",
                "resource": "ec2",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "CPUUtilization",
                        "days": 3,
                        "period": 86400,
                        "value": 1,
                        "op": "lte"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestPropagateSpotTags(BaseTest):

    def test_propagate_spot(self):
        session_factory = self.replay_flight_data("test_ec2_propagate_spot_tags")

        policy = self.load_policy(
            {
                "name": "ec2-spot",
                "resource": "ec2",
                "query": [{"instance-id": "i-01db165f1452ef5e4"}],
                "actions": [{"type": "propagate-spot-tags", "only_tags": ["Name"]}],
            },
            session_factory=session_factory,
        )

        policy.run()
        client = session_factory().client("ec2")
        tags = {
            t["Key"]: t["Value"]
            for t in client.describe_tags(
                Filters=[{"Name": "resource-id", "Values": ["i-01db165f1452ef5e4"]}]
            ).get(
                "Tags", []
            )
        }
        self.assertEqual(tags, {"Name": "Test"})


class TestDisableApiTermination(BaseTest):

    def test_term_prot_enabled(self):
        session_factory = self.replay_flight_data(
            "test_ec2_termination-protected_filter"
        )
        policy = self.load_policy(
            {
                "name": "ec2-termination-enabled",
                "resource": "ec2",
                "filters": [{"type": "termination-protected"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["InstanceId"], "i-092f500eaad726b71")

    def test_term_prot_not_enabled(self):
        session_factory = self.replay_flight_data(
            "test_ec2_termination-protected_filter"
        )
        policy = self.load_policy(
            {
                "name": "ec2-termination-NOT-enabled",
                "resource": "ec2",
                "filters": [{"not": [{"type": "termination-protected"}]}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            sorted([x["InstanceId"] for x in resources]),
            ["i-02117c13e1d21b229", "i-0718418de3bb4ae2a"],
        )

    def test_policy_permissions(self):
        session_factory = self.replay_flight_data(
            "test_ec2_termination-protected_filter"
        )
        policy = self.load_policy(
            {
                "name": "ec2-termination-enabled",
                "resource": "ec2",
                "filters": [{"type": "termination-protected"}],
            },
            session_factory=session_factory,
        )
        perms = policy.get_permissions()
        self.assertEqual(
            perms,
            {
                "ec2:DescribeInstances",
                "ec2:DescribeTags",
                "ec2:DescribeInstanceAttribute",
            },
        )


class TestEc2Permissions(BaseTest):

    def test_ec2_permissions(self):
        factory = self.replay_flight_data('test_ec2_permissions')
        policy = self.load_policy({
            'name': 'ec2-perm',
            'resource': 'aws.ec2',
            'filters': [{
                'type': 'check-permissions',
                'match': 'allowed',
                'actions': ['lambda:CreateFunction']}]},
            session_factory=factory, config={'region': 'us-west-2'})
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('c7n:perm-matches' in resources[0])


class TestSsm(BaseTest):

    def test_ssm_status(self):
        session_factory = self.replay_flight_data('test_ec2_ssm_filter')
        policy = self.load_policy({
            'name': 'ec2-ssm',
            'resource': 'aws.ec2',
            'filters': [
                {'type': 'ssm',
                 'key': 'PlatformName',
                 'value': 'Ubuntu'},
                {'type': 'ssm',
                 'key': 'PingStatus',
                 'value': 'Online'}]},
            session_factory=session_factory,
            config={'region': 'us-east-2'})
        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertTrue('c7n:SsmState' in resources[0])
        self.assertEqual(
            [r['InstanceId'] for r in resources],
            ['i-0dea82d960d56dc1d', 'i-0ba3874e85bb97244'])

    def test_ssm_compliance(self):
        session_factory = self.replay_flight_data('test_ec2_ssm_compliance_filter')
        policy = self.load_policy({
            'name': 'ec2-ssm-compliance',
            'resource': 'aws.ec2',
            'filters': [
                {'type': 'ssm-compliance',
                 'compliance_types': [
                     'Association',
                     'Patch'
                 ],
                 'severity': [
                     'CRITICAL',
                     'HIGH',
                     'MEDIUM',
                     'LOW',
                     'UNSPECIFIED'
                 ],
                 'states': ['NON_COMPLIANT']}]},
            session_factory=session_factory,
            config={'region': 'us-east-2'})
        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertTrue('c7n:ssm-compliance' in resources[0])
        self.assertEqual(
            [r['InstanceId'] for r in resources],
            ['i-0dea82d960d56dc1d', 'i-0ba3874e85bb97244'])

    def test_ssm_inventory(self):
        session_factory = self.replay_flight_data("test_ec2_ssm_inventory_filter")
        p = self.load_policy(
            {
                "name": "ec2-find-specific-package",
                "resource": "ec2",
                "filters": [
                    {
                        "type": "ssm-inventory",
                        "query": [
                            {
                                "Key": "Name",
                                "Values": [
                                    "docker"
                                ],
                                "Type": "Equal"
                            }
                        ]
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('c7n:SSM-Inventory' in resources[0])
        self.assertEqual(resources[0]['InstanceId'], 'i-069d5df3524c95b06')


class TestHealthEventsFilter(BaseTest):

    def test_ec2_health_events_filter(self):
        session_factory = self.replay_flight_data("test_ec2_health_events_filter")
        policy = self.load_policy(
            {
                "name": "ec2-health-events-filter",
                "resource": "ec2",
                "filters": [{"type": "health-event"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestTagTrim(BaseTest):

    def test_ec2_tag_trim(self):
        self.patch(tags.TagTrim, "max_tag_count", 10)
        session_factory = self.replay_flight_data("test_ec2_tag_trim")
        ec2 = session_factory().client("ec2")
        start_tags = {
            t["Key"]: t["Value"]
            for t in ec2.describe_tags(
                Filters=[{"Name": "resource-id", "Values": ["i-fdb01920"]}]
            )[
                "Tags"
            ]
        }
        policy = self.load_policy(
            {
                "name": "ec2-tag-trim",
                "resource": "ec2",
                "filters": [{"type": "tag-count", "count": 10}],
                "actions": [
                    {
                        "type": "tag-trim",
                        "space": 1,
                        "preserve": [
                            "Name",
                            "Env",
                            "Account",
                            "Platform",
                            "Classification",
                            "Planet",
                        ],
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        end_tags = {
            t["Key"]: t["Value"]
            for t in ec2.describe_tags(
                Filters=[{"Name": "resource-id", "Values": ["i-fdb01920"]}]
            )[
                "Tags"
            ]
        }

        self.assertEqual(len(start_tags) - 1, len(end_tags))
        self.assertTrue("Containers" in start_tags)
        self.assertFalse("Containers" in end_tags)


class TestVolumeFilter(BaseTest):

    def test_ec2_attached_ebs_filter(self):
        session_factory = self.replay_flight_data("test_ec2_attached_ebs_filter")
        policy = self.load_policy(
            {
                "name": "ec2-unencrypted-vol",
                "resource": "ec2",
                "filters": [{"type": "ebs", "key": "Encrypted", "value": False}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    # DISABLED / Re-record flight data on public account
    def test_ec2_attached_volume_skip_block(self):
        session_factory = self.replay_flight_data("test_ec2_attached_ebs_filter")
        policy = self.load_policy(
            {
                "name": "ec2-unencrypted-vol",
                "resource": "ec2",
                "filters": [
                    {
                        "type": "ebs",
                        "skip-devices": ["/dev/sda1", "/dev/xvda", "/dev/sdb1"],
                        "key": "Encrypted",
                        "value": False,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 0)


class TestResizeInstance(BaseTest):

    def test_ec2_resize_cost_hub(self):
        factory = self.replay_flight_data("test_ec2_costhub_resize", region="us-east-2")
        policy = self.load_policy(
            {"name": "ec2-hub-resize",
             "resource": "ec2",
             "filters": ["cost-optimization"],
             "actions": ["resize"]},
            config={"region": "us-east-2"},
            session_factory=factory
        )

        client = factory().client('ec2', region_name='us-east-2')
        resources = policy.run()
        assert len(resources) == 1
        instances = utils.query_instances(
            None, client=client, InstanceIds=[r["InstanceId"] for r in resources]
        )
        assert resources[0]["InstanceType"] != instances[0]["InstanceType"]

    def test_ec2_resize(self):
        # preconditions - three instances (2 m4.4xlarge, 1 m4.1xlarge)
        # one of the instances stopped
        session_factory = self.replay_flight_data("test_ec2_resize")
        policy = self.load_policy(
            {
                "name": "ec2-resize",
                "resource": "ec2",
                "filters": [
                    {
                        "type": "value",
                        "key": "State.Name",
                        "value": ["running", "stopped"],
                        "op": "in",
                    },
                    {
                        "type": "value",
                        "key": "InstanceType",
                        "value": ["m4.2xlarge", "m4.4xlarge"],
                        "op": "in",
                    },
                ],
                "actions": [
                    {
                        "type": "resize",
                        "restart": True,
                        "default": "m4.large",
                        "type-map": {"m4.4xlarge": "m4.2xlarge"},
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 3)

        stopped, running = [], []
        for i in resources:
            if i["State"]["Name"] == "running":
                running.append(i["InstanceId"])
            if i["State"]["Name"] == "stopped":
                stopped.append(i["InstanceId"])

        instances = utils.query_instances(
            session_factory(), InstanceIds=[r["InstanceId"] for r in resources]
        )

        cur_stopped, cur_running = [], []
        for i in instances:
            if i["State"]["Name"] == "running":
                cur_running.append(i["InstanceId"])
            if i["State"]["Name"] == "stopped":
                cur_stopped.append(i["InstanceId"])

        cur_running.sort()
        running.sort()

        self.assertEqual(cur_stopped, stopped)
        self.assertEqual(cur_running, running)
        instance_types = [i["InstanceType"] for i in instances]
        instance_types.sort()
        self.assertEqual(
            instance_types, list(sorted(["m4.large", "m4.2xlarge", "m4.2xlarge"]))
        )


class TestStateTransitionAgeFilter(BaseTest):

    def test_ec2_state_transition_age(self):
        session_factory = self.replay_flight_data(
            "test_ec2_state_transition_age_filter"
        )
        policy = self.load_policy(
            {
                "name": "ec2-state-transition-age",
                "resource": "ec2",
                "filters": [
                    {"State.Name": "running"}, {"type": "state-age", "days": 30}
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        # compare stateTransition reason to expected
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["StateTransitionReason"],
            "User initiated (2015-11-25 10:11:55 GMT)",
        )

    def test_date_parsing(self):
        instance = ec2.StateTransitionAge(None)

        # Missing key
        self.assertIsNone(instance.get_resource_date({}))

        # Bad date format
        self.assertRaises(
            ValueError,
            instance.get_resource_date,
            {"StateTransitionReason": "User initiated (201-02-06 17:77:00 GMT)"},
        )

        # Won't match regex
        self.assertIsNone(
            instance.get_resource_date(
                {"StateTransitionReason": "Server.InternalError"}
            )
        )

        # Test for success
        self.assertEqual(
            instance.get_resource_date(
                {"StateTransitionReason": "User initiated (2017-02-06 17:57:00 GMT)"}
            ),
            datetime.datetime(2017, 2, 6, 17, 57, tzinfo=tz.tzutc()),
        )


class TestImageAgeFilter(BaseTest):

    def test_ec2_image_age(self):
        session_factory = self.replay_flight_data("test_ec2_image_age_filter")
        policy = self.load_policy(
            {
                "name": "ec2-image-age",
                "resource": "ec2",
                "filters": [
                    {"State.Name": "running"}, {"type": "image-age", "days": 30}
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestImageAncestryFilter(BaseTest):

    def test_ec2_image_ancestry(self):
        session_factory = self.replay_flight_data("test_ec2_image_ancestry")
        policy = self.load_policy(
            {
                "name": "ec2-image-ancestry",
                "resource": "ec2",
                "filters": [
                    {"type": "image-ancestry", "approved_owners": ["amazon"]}
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestImageFilter(BaseTest):

    def test_ec2_image(self):
        session_factory = self.replay_flight_data("test_ec2_image_filter")
        policy = self.load_policy(
            {
                "name": "ec2-image",
                "resource": "ec2",
                "filters": [{"type": "image", "key": "Public", "value": True}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["InstanceId"], "i-039628786cabe8c16")


class TestInstanceAge(BaseTest):

    # placebo doesn't record tz information
    def test_ec2_instance_age(self):
        session_factory = self.replay_flight_data("test_ec2_instance_age_filter")
        policy = self.load_policy(
            {
                "name": "ec2-instance-age",
                "resource": "ec2",
                "filters": [
                    {"State.Name": "running"}, {"type": "instance-age", "days": 0}
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestTag(BaseTest):

    def test_ec2_tag(self):
        session_factory = self.replay_flight_data("test_ec2_mark")
        policy = self.load_policy(
            {
                "name": "ec2-test-mark",
                "resource": "ec2",
                "filters": [{"State.Name": "running"}],
                "actions": [{"type": "tag", "key": "Testing", "value": "Testing123"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_ec2_tag_errors(self):
        # Specifying both 'key' and 'tag' is an error
        policy = {
            "name": "ec2-tag-error",
            "resource": "ec2",
            "actions": [
                {"type": "tag", "key": "Testing", "tag": "foo", "value": "TestingError"}
            ],
        }
        self.assertRaises(PolicyValidationError, self.load_policy, policy)

        # Invalid op for 'mark-for-op' action
        policy = {
            "name": "ec2-tag-error",
            "resource": "ec2",
            "actions": [{"type": "mark-for-op", "op": "fake"}],
        }
        self.assertRaises(PolicyValidationError, self.load_policy, policy)

    def test_ec2_untag(self):
        session_factory = self.replay_flight_data("test_ec2_untag")
        policy = self.load_policy(
            {
                "name": "ec2-test-unmark",
                "resource": "ec2",
                "filters": [{"tag:Testing": "not-null"}],
                "actions": [{"type": "remove-tag", "tags": ["Testing"]}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_ec2_untag_array(self):
        session_factory = self.replay_flight_data("test_ec2_untag_array")
        policy = self.load_policy(
            {
                "name": "ec2-test-unmark-array",
                "resource": "ec2",
                "filters": [{"tag:Testing": "not-null"}],
                "actions": [
                    {
                        "type": "remove-tag",
                        "tags": ["Testing", "TestingTwo", "TestingThree"],
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_ec2_normalize_tag(self):
        session_factory = self.replay_flight_data("test_ec2_normalize_tag")

        policy = self.load_policy(
            {
                "name": "ec2-test-normalize-tag-lower",
                "resource": "ec2",
                "filters": [{"tag:Testing-lower": "not-null"}],
                "actions": [
                    {"type": "normalize-tag", "key": "Testing-lower", "action": "lower"}
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        policy = self.load_policy(
            {
                "name": "ec2-test-normalize-tag-upper",
                "resource": "ec2",
                "filters": [{"tag:Testing-upper": "not-null"}],
                "actions": [
                    {"type": "normalize-tag", "key": "Testing-upper", "action": "upper"}
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        policy = self.load_policy(
            {
                "name": "ec2-test-normalize-tag-title",
                "resource": "ec2",
                "filters": [{"tag:Testing-title": "not-null"}],
                "actions": [
                    {"type": "normalize-tag", "key": "Testing-title", "action": "title"}
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        policy = self.load_policy(
            {
                "name": "ec2-test-normalize-tag-strip",
                "resource": "ec2",
                "filters": [{"tag:Testing-strip": "not-null"}],
                "actions": [
                    {
                        "type": "normalize-tag",
                        "key": "Testing-strip",
                        "action": "strip",
                        "value": "blah",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_ec2_rename_tag(self):
        session_factory = self.replay_flight_data("test_ec2_rename_tag")

        policy = self.load_policy(
            {
                "name": "ec2-rename-start",
                "resource": "ec2",
                "filters": [{"tag:Testing": "present"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 3)

        policy = self.load_policy(
            {
                "name": "ec2-rename-tag",
                "resource": "ec2",
                "actions": [
                    {"type": "rename-tag", "old_key": "Testing", "new_key": "Testing1"}
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 4)

        policy = self.load_policy(
            {
                "name": "ec2-rename-end",
                "resource": "ec2",
                "filters": [{"tag:Testing1": "present"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 3)

    def test_ec2_mark_zero(self):
        localtz = tz.gettz("America/New_York")
        dt = datetime.datetime.now(localtz)
        dt = dt.replace(year=2017, month=11, day=24, hour=7, minute=00)
        session_factory = self.replay_flight_data("test_ec2_mark_zero")
        session = session_factory(region="us-east-1")
        ec2 = session.client("ec2")
        resource = ec2.describe_instances(InstanceIds=["i-04d3e0630bd342566"])[
            "Reservations"
        ][
            0
        ][
            "Instances"
        ][
            0
        ]
        tags = [t["Value"] for t in resource["Tags"] if t["Key"] == "maid_status"]
        self.assertEqual(len(tags), 0)

        policy = self.load_policy(
            {
                "name": "ec2-mark-zero-days",
                "resource": "ec2",
                "filters": [{"tag:CreatorName": "joshuaroot"}],
                "actions": [{"type": "mark-for-op", "days": 0, "op": "terminate"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["InstanceId"], "i-04d3e0630bd342566")

        resource = ec2.describe_instances(InstanceIds=["i-04d3e0630bd342566"])[
            "Reservations"
        ][
            0
        ][
            "Instances"
        ][
            0
        ]
        tags = [t["Value"] for t in resource["Tags"] if t["Key"] == "maid_status"]
        result = datetime.datetime.strptime(
            tags[0].strip().split("@", 1)[-1], "%Y/%m/%d"
        ).replace(
            tzinfo=localtz
        )
        self.assertEqual(result.date(), dt.date())

    def test_ec2_mark_hours(self):
        localtz = tz.gettz("America/New_York")
        dt = datetime.datetime.now(localtz)
        dt = dt.replace(
            year=2018, month=2, day=20, hour=18, minute=00, second=0, microsecond=0
        )
        session_factory = self.replay_flight_data("test_ec2_mark_hours")
        session = session_factory(region="us-east-1")
        ec2 = session.client("ec2")

        policy = self.load_policy(
            {
                "name": "ec2-mark-5-hours",
                "resource": "ec2",
                "filters": [
                    {"tag:hourly-mark": "absent"}, {"tag:CreatorName": "joshuaroot"}
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "hourly-mark",
                        "hours": 3,
                        "op": "stop",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        resource = ec2.describe_instances(InstanceIds=[resources[0]["InstanceId"]])[
            "Reservations"
        ][
            0
        ][
            "Instances"
        ][
            0
        ]
        tags = [t["Value"] for t in resource["Tags"] if t["Key"] == "hourly-mark"]
        result = datetime.datetime.strptime(
            tags[0].strip().split("@", 1)[-1], "%Y/%m/%d %H%M %Z"
        ).replace(
            tzinfo=localtz
        )
        self.assertEqual(result, dt)

    def test_ec2_marked_hours(self):
        session_factory = self.replay_flight_data("test_ec2_marked_hours")
        policy = self.load_policy(
            {
                "name": "ec2-mark-5-hours",
                "resource": "ec2",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "hourly-mark",
                        "op": "stop",
                        "skew_hours": 3,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["InstanceId"], "i-098dae2615acb5809")

    def test_ec2_multiple_mark_for_op_tags(self):
        session_factory = self.replay_flight_data("test_ec2_multiple_mark_for_op_tags")
        policy = self.load_policy(
            {
                "name": "ec2-mark-for-op-tags",
                "resource": "ec2",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "c7n-tag-compliance",
                        "op": "terminate"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 3)


class TestStop(BaseTest):

    def test_ec2_stop(self):
        session_factory = self.replay_flight_data("test_ec2_stop")
        policy = self.load_policy(
            {
                "name": "ec2-test-stop",
                "resource": "ec2",
                "filters": [{"tag:Testing": "not-null"}],
                "actions": [{"type": "stop"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

    def test_ec2_stop_hibernate(self):
        session_factory = self.replay_flight_data("test_ec2_stop_hibernate")
        policy = self.load_policy(
            {
                "name": "ec2-test-stop-hibernate",
                "resource": "ec2",
                "query": [{"tag-key": "Testing"}],
                "actions": [{"type": "stop", "hibernate": True}],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 2)

        if self.recording:
            time.sleep(25)

        instances = utils.query_instances(
            session_factory(), InstanceIds=[r["InstanceId"] for r in resources]
        )

        stopped = [
            i
            for i in instances
            if i["StateReason"]["Code"] == "Client.UserInitiatedShutdown"
        ]
        hibernated = [
            i
            for i in instances
            if i["StateReason"]["Code"] == "Client.UserInitiatedHibernate"
        ]

        self.assertEqual(len(stopped), 1)
        self.assertEqual(len(hibernated), 1)

    def test_ec2_stop_with_protection_enabled(self):
        # Test conditions: single running instance, with stop protection
        session_factory = self.replay_flight_data("test_ec2_stop_with_protection_enabled")
        policy = self.load_policy(
            {
                "name": "ec2-test-stop-with-protection-enabled",
                "resource": "ec2",
                "filters": [{"InstanceId": "i-000b2f5125402eb55"}],
                "actions": [{"type": "stop", "force": True}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        perms = policy.get_permissions()
        self.assertTrue("ec2:ModifyInstanceAttribute" in perms)

        instances = utils.query_instances(
            session_factory(), InstanceIds=["i-000b2f5125402eb55"]
        )
        self.assertEqual(instances[0]["State"]["Name"], "stopped")

    def test_ec2_stop_with_protection_enabled_handle_error(self):
        policy = self.load_policy(
            {
                "name": "ec2-test-stop-with-protection-enabled",
                "resource": "ec2",
                "filters": [{"InstanceId": "i-000b2f5125402eb55"}],
                "actions": [{"type": "stop", "force": True}],
            }
        )

        stop_action = policy.resource_manager.actions[0]

        client = mock.MagicMock()
        client.modify_instance_attribute.side_effect = ClientError(
            {'Error': {
                'Code': 'IncorrectInstanceState',
                'Message': ("The instance 'i-000b2f5125402eb55' must be in a "
                            "'running', 'pending', 'stopping' or "
                            "'stopped' state for this operation")
            }}, 'ModifyInstanceAttribute')

        self.assertEqual(
            None,
            stop_action.disable_protection(client, 'stop', [{'InstanceId': 'i-foo'}]),
        )

        client2 = mock.MagicMock()
        client2.modify_instance_attribute.side_effect = ClientError(
            {'Error': {
                'Code': 'UnauthorizedOperation',
                'Message': "You are not authorized to perform this operation."
            }}, 'ModifyInstanceAttribute')

        self.assertRaises(
            ClientError,
            stop_action.disable_protection,
            client2, 'stop', [{'InstanceId': 'i-foo'}],
        )

    def test_ec2_stop_with_protection_enabled_ephemeral(self):
        # Test conditions: single running instance (ephemeral), with stop protection
        session_factory = self.replay_flight_data("test_ec2_stop_with_protection_enabled_ephemeral")
        policy = self.load_policy(
            {
                "name": "ec2-test-stop-with-protection-enabled-ephemeral",
                "resource": "ec2",
                "filters": [{"InstanceId": "i-0a3e363a5366795dd"}],
                "actions": [{"type": "stop", "terminate-ephemeral": True, "force": True}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        perms = policy.get_permissions()
        self.assertTrue("ec2:ModifyInstanceAttribute" in perms)

        instances = utils.query_instances(
            session_factory(), InstanceIds=["i-0a3e363a5366795dd"]
        )
        self.assertEqual(instances[0]["State"]["Name"], "terminated")


class TestReboot(BaseTest):

    def test_ec2_reboot(self):
        session_factory = self.replay_flight_data("test_ec2_reboot")
        policy = self.load_policy(
            {
                "name": "ec2-test-reboot",
                "resource": "ec2",
                "filters": [{"tag:Testing": "not-null"}],
                "actions": [{"type": "reboot"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 2)
        running = []
        for i in resources:
            if i["State"]["Name"] == "running":
                running.append(i["InstanceId"])
        if self.recording:
            time.sleep(25)
        instances = utils.query_instances(
            session_factory(), InstanceIds=[r["InstanceId"] for r in resources]
        )

        cur_running = []
        for i in instances:
            if i["State"]["Name"] == "running":
                cur_running.append(i["InstanceId"])

        cur_running.sort()
        running.sort()

        self.assertEqual(cur_running, running)


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


class TestOr(BaseTest):

    def test_ec2_or_condition(self):
        session_factory = self.replay_flight_data("test_ec2_stop")
        policy = self.load_policy(
            {
                "name": "ec2-test-snapshot",
                "resource": "ec2",
                "filters": [
                    {"or": [{"tag:Name": "CompileLambda"}, {"tag:Name": "Spinnaker"}]}
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            sorted([r["InstanceId"] for r in resources]), [u"i-13413bd7", u"i-1aebf7c0"]
        )


class TestSnapshot(BaseTest):

    def test_ec2_snapshot_error_process_set(self):
        p = self.load_policy({
            'name': 'ec2-test-snapshot', "resource": "ec2",
            "actions": [{"type": "snapshot"}]})
        snapshotter = p.resource_manager.actions[0]

        def process_volume_set(client, resource):
            raise ValueError('something bad happened')

        snapshotter.process_volume_set = process_volume_set
        log = self.capture_logging('custodian.actions')
        self.assertRaises(
            ValueError, snapshotter.process, [{'InstanceId': 'xyz'}])
        self.assertTrue('something' in log.getvalue())

    def test_ec2_snapshot_error_process_once(self):
        p = self.load_policy({
            'name': 'ec2-test-snapshot', "resource": "ec2",
            "actions": [{"type": "snapshot"}]})

        log = self.capture_logging('custodian.actions')
        snapshotter = p.resource_manager.actions[0]
        client = mock.Mock(['create_snapshots'])
        err_response = {'Error': {'Code': 'InvalidInstanceId.NotFound'}}
        err = ClientError(err_response, 'create_snapshots')
        client.create_snapshots.side_effect = err
        snapshotter.process_volume_set(client, {'InstanceId': 'i-foo'})
        client.create_snapshots.assert_called_once()

        self.assertTrue('i-foo' in log.getvalue())
        err_response['Error']['Code'] = 'InvalidRequest'
        self.assertRaises(
            ClientError,
            snapshotter.process_volume_set,
            client, {'InstanceId': 'i-foo'})

    def test_ec2_snapshot_validate(self):
        templ = {
            "name": "ec2-test-snapshot",
            "resource": "ec2",
            "filters": [{"tag:Name": "CompileLambda"}],
            "actions": [{"type": "snapshot"}]}

        self.load_policy(templ)
        templ['actions'][0]['copy-volume-tags'] = False
        self.load_policy(templ)
        templ['actions'][0]['copy-tags'] = ['Name']
        self.assertRaises(PolicyValidationError, self.load_policy, templ)

    def test_ec2_snapshot_copy_instance_tags_default(self):
        session_factory = self.replay_flight_data("test_ec2_snapshot")
        policy = self.load_policy(
            {
                "name": "ec2-test-snapshot",
                "resource": "ec2",
                "filters": [{"tag:Name": "Foo"}],
                "actions": [{"type": "snapshot"}]
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('ec2')
        snaps = client.describe_snapshots(
            SnapshotIds=resources[0]['c7n:snapshots']).get('Snapshots')
        rtags = {t['Key']: t['Value'] for t in resources[0]['Tags']}
        for s in snaps:
            self.assertEqual(rtags, {t['Key']: t['Value'] for t in s['Tags']})

    def test_ec2_snapshot_copy_tags(self):
        session_factory = self.replay_flight_data("test_ec2_snapshot_copy_tags")
        policy = self.load_policy(
            {
                "name": "ec2-test-snapshot",
                "resource": "ec2",
                "filters": [{"tag:Name": "Foo"}],
                "actions": [{"type": "snapshot", "copy-tags": ['Name', 'Stage']}]
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('ec2')
        snaps = client.describe_snapshots(
            SnapshotIds=resources[0]['c7n:snapshots']).get('Snapshots')
        rtags = {t['Key']: t['Value'] for t in resources[0]['Tags']}
        rtags.pop('App')
        rtags['custodian_snapshot'] = ''
        for s in snaps:
            self.assertEqual(rtags, {t['Key']: t['Value'] for t in s['Tags']})

    def test_ec2_snapshot_tags(self):
        session_factory = self.replay_flight_data("test_ec2_snapshot_tags")
        policy = self.load_policy(
            {
                "name": "ec2-test-snapshot",
                "resource": "ec2",
                "filters": [{"tag:Name": "Foo"}],
                "actions": [{"type": "snapshot", "copy-tags": ['Name', 'Stage'],
                             "tags": {"test-tag": 'custodian'}}]
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('ec2')
        snaps = client.describe_snapshots(
            SnapshotIds=resources[0]['c7n:snapshots']).get('Snapshots')
        rtags = {t['Key']: t['Value'] for t in resources[0]['Tags']}
        rtags.pop('App')
        rtags['test-tag'] = 'custodian'
        for s in snaps:
            self.assertEqual(rtags, {t['Key']: t['Value'] for t in s['Tags']})
            self.assertEqual(s['Description'], "Snapshot Created for i-063c6794763254b51 (Foo)")


class TestSetInstanceProfile(BaseTest):

    def test_ec2_set_instance_profile_missing(self):
        factory = self.replay_flight_data(
            'test_ec2_set_instance_profile_missing')
        p = self.load_policy({
            'name': 'ec2-set-profile-missing',
            'resource': 'ec2',
            'filters': [{'IamInstanceProfile': 'absent'}],
            'actions': [
                {
                    'type': 'set-instance-profile',
                    'name': 'aws-opsworks-ec2-role'
                }
            ]},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertFalse(resources[0].get('IamInstanceProfile'))

        client = factory().client('ec2')
        associations = {
            a['InstanceId']: a['IamInstanceProfile']['Arn']
            for a in client.describe_iam_instance_profile_associations(
                Filters=[
                    {'Name': 'instance-id',
                     'Values': [i['InstanceId'] for i in resources]},
                    {'Name': 'state', 'Values': ['associating', 'associated']}]
            ).get('IamInstanceProfileAssociations', ())}
        self.assertEqual(
            associations,
            {resources[0]['InstanceId']: 'arn:aws:iam::644160558196:instance-profile/aws-opsworks-ec2-role'}) # noqa

    def test_ec2_set_instance_profile_existing(self):
        factory = self.replay_flight_data(
            'test_ec2_set_instance_profile_existing')
        p = self.load_policy({
            'name': 'ec2-set-profile-extant',
            'resource': 'ec2',
            'filters': [{'tag:Name': 'role-test'}],
            'actions': [{
                'type': 'set-instance-profile',
                'name': 'ecsInstanceRole'}]}, session_factory=factory)
        client = factory().client('ec2')
        resources = p.run()
        # 3 instances covering no role, target role, different role.
        self.assertEqual(len(resources), 3)
        previous_associations = {
            i['InstanceId']: i.get('IamInstanceProfile', {}).get('Arn')
            for i in resources}
        self.assertEqual(
            previous_associations,
            {u'i-01b7ee380879d3fd8': u'arn:aws:iam::644160558196:instance-profile/CloudCustodianRole', # noqa
             u'i-06305b4b9f5e3f8b8': u'arn:aws:iam::644160558196:instance-profile/ecsInstanceRole',
             u'i-0aef5d5ffb60c8615': None})

        # verify changes
        associations = {
            a['InstanceId']: a['IamInstanceProfile']['Arn']
            for a in client.describe_iam_instance_profile_associations(
                Filters=[
                    {'Name': 'instance-id',
                     'Values': [i['InstanceId'] for i in resources]},
                    {'Name': 'state', 'Values': ['associating', 'associated']}]
            ).get('IamInstanceProfileAssociations', ())}
        self.assertEqual(
            associations,
            {'i-01b7ee380879d3fd8': 'arn:aws:iam::644160558196:instance-profile/ecsInstanceRole',
             'i-06305b4b9f5e3f8b8': 'arn:aws:iam::644160558196:instance-profile/ecsInstanceRole',
             'i-0aef5d5ffb60c8615': 'arn:aws:iam::644160558196:instance-profile/ecsInstanceRole'})

    def test_ec2_set_instance_profile_disassocation(self):
        session_factory = self.replay_flight_data(
            "test_ec2_set_instance_profile_disassociation"
        )
        policy = self.load_policy(
            {
                "name": "ec2-test-set-instance-profile-disassociation",
                "resource": "ec2",
                "filters": [
                    {"tag:Name": "MissingInstanceProfile"},
                    {
                        "type": "value",
                        "key": "IamInstanceProfile.Arn",
                        "op": "regex",
                        "value": ".*/ec2-default",
                    },
                ],
                "actions": [{"type": "set-instance-profile"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertGreaterEqual(len(resources), 1)
        ec2 = session_factory().client("ec2")
        associations = ec2.describe_iam_instance_profile_associations(
            Filters=[
                {"Name": "instance-id", "Values": [r["InstanceId"] for r in resources]}
            ]
        )

        for a in associations["IamInstanceProfileAssociations"]:
            self.assertIn(a["State"], ("disassociating", "disassociated"))


class TestEC2QueryParser(unittest.TestCase):

    def test_query(self):
        self.assertEqual(EC2QueryParser.parse([]), [])
        x = EC2QueryParser.parse([{"instance-state-name": "running"}])
        self.assertEqual(
            x[0]['Filters'][0], {"Name": "instance-state-name", "Values": ["running"]}
        )
        query = [
            {'Filters':
                    [
                        {'Name': 'tag:Name', 'Values': ['Instance1']},
                        {'Name': 'instance-state-name', 'Values': ['running']}
                    ]
            },
            {'InstanceIds': ['i-123abc', 'i-abc123']},
            {'MaxResults': 1000},
        ]

        self.assertEqual(EC2QueryParser.parse(query), query)

        self.assertEqual(
            EC2QueryParser.parse([{"tag:ASV": "REALTIMEMSG"}]), [
                {"Filters": [{"Name": "tag:ASV", "Values": ["REALTIMEMSG"]}]}])

        self.assertEqual(
            EC2QueryParser.parse([{"tag:Test": "Value1"}, {"tag:Test": "Value2"}]),
                [{"Filters": [{"Name": "tag:Test", "Values": ["Value1", "Value2"]}]}])

    def test_invalid_query(self):
        self.assertRaises(PolicyValidationError, EC2QueryParser.parse, [{"tag:ASV": None}])

        self.assertRaises(
            PolicyValidationError, EC2QueryParser.parse, [
                {'Filters': [{'instance-state-name': 'running'}]}])

        self.assertRaises(PolicyValidationError, EC2QueryParser.parse, [{'InstanceIds': None}])

        self.assertRaises(PolicyValidationError, EC2QueryParser.parse, [{'InstanceIds': [1]}])

        self.assertRaises(PolicyValidationError, EC2QueryParser.parse,
                          [{'Filters': [{'Name': 'architecture', 'Values': ['gothic']}]}])

        self.assertRaises(PolicyValidationError, EC2QueryParser.parse, [{"tag:ASV": None}])

        self.assertRaises(PolicyValidationError, EC2QueryParser.parse,
                          [{'Filters': [{'Name': 'instance-group-name', 'Values': [False]}]}])

        self.assertRaises(PolicyValidationError, EC2QueryParser.parse, [{'MaxResults': '1000'}])

        self.assertRaises(PolicyValidationError, EC2QueryParser.parse,
                          [{'Filters': {'Name': 'instance-group-name', 'Values': ["Value1"]}}])


class TestTerminate(BaseTest):

    def test_ec2_terminate(self):
        # Test conditions: single running instance, with delete protection
        session_factory = self.replay_flight_data("test_ec2_terminate")
        p = self.load_policy(
            {
                "name": "ec2-term",
                "resource": "ec2",
                "filters": [{"InstanceId": "i-017cf4e2a33b853fe"}],
                "actions": [{"type": "terminate", "force": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        instances = utils.query_instances(
            session_factory(), InstanceIds=["i-017cf4e2a33b853fe"]
        )
        self.assertEqual(instances[0]["State"]["Name"], "shutting-down")

    def test_ec2_terminate_with_protection_enabled(self):
        # Test conditions: single running instance, with delete protection
        session_factory = self.replay_flight_data("test_ec2_terminate_with_protection_enabled")
        p = self.load_policy(
            {
                "name": "ec2-term",
                "resource": "ec2",
                "filters": [{"InstanceId": "i-017fc9a2a33b853fe"}],
                "actions": [{"type": "terminate", "force": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        instances = utils.query_instances(
            session_factory(), InstanceIds=["i-017fc9a2a33b853fe"]
        )
        self.assertEqual(instances[0]["State"]["Name"], "shutting-down")


class TestDefaultVpc(BaseTest):

    def test_ec2_default_vpc(self):
        session_factory = self.replay_flight_data("test_ec2_default_vpc")
        p = self.load_policy(
            {
                "name": "ec2-default-filters",
                "resource": "ec2",
                "filters": [{"type": "default-vpc"}],
            },
            config={"region": "us-west-2"},
            session_factory=session_factory,
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["InstanceId"], "i-0bfe468063b02d018")


class TestSingletonFilter(BaseTest):

    def test_ec2_singleton_filter(self):
        session_factory = self.replay_flight_data("test_ec2_singleton")
        p = self.load_policy(
            {
                "name": "ec2-singleton-filters",
                "resource": "ec2",
                "filters": [{"tag:Name": "Singleton"}, {"type": "singleton"}],
            },
            config={"region": "us-west-1"},
            session_factory=session_factory,
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["InstanceId"], "i-00fe7967fb7167c62")


class TestOffHoursFilter(BaseTest):

    def test_ec2_offhours_filter(self):
        session_factory = self.replay_flight_data("test_ec2_offhours_filter")

        t = datetime.datetime.now(tz.gettz("America/New_York"))
        t = t.replace(year=2020, month=2, day=11, hour=19, minute=00)

        with mock_datetime_now(t, datetime):
            p = self.load_policy(
                {
                    "name": "ec2-offhours",
                    "resource": "ec2",
                    "query": [{"tag-key": "c7n_test"}],
                    "filters": [
                        {
                            "type": "offhour",
                            "offhour": 19,
                            "tag": "custodian_downtime",
                            "default_tz": "utc",
                            "opt-out": True,
                            "weekends": False,
                        },
                    ],
                },
                config={"region": "us-west-2"},
                session_factory=session_factory,
            )

            resources = p.run()
            self.assertEqual(len(resources), 1)

    def test_ec2_offhours_no_filter(self):
        session_factory = self.replay_flight_data("test_ec2_offhours_no_filter")

        t = datetime.datetime.now(tz.gettz("America/New_York"))
        t = t.replace(year=2020, month=2, day=11, hour=19, minute=00)

        with mock_datetime_now(t, datetime):
            p = self.load_policy(
                {
                    "name": "ec2-offhours",
                    "resource": "ec2",
                    "query": [{"tag-key": "c7n_test"}],
                    "filters": [
                        {
                            "type": "offhour",
                            "offhour": 19,
                            "tag": "custodian_downtime",
                            "default_tz": "utc",
                            "opt-out": True,
                            "weekends": False,
                            "state-filter": False,
                        },
                    ],
                },
                config={"region": "us-west-2"},
                session_factory=session_factory,
            )

            resources = p.run()
            self.assertEqual(len(resources), 2)


class TestOnHoursFilter(BaseTest):

    def test_ec2_onhours_filter(self):
        session_factory = self.replay_flight_data("test_ec2_onhours_filter")

        t = datetime.datetime.now(tz.gettz("America/New_York"))
        t = t.replace(year=2020, month=2, day=11, hour=7, minute=00)

        with mock_datetime_now(t, datetime):
            p = self.load_policy(
                {
                    "name": "ec2-onhours",
                    "resource": "ec2",
                    "query": [{"tag-key": "c7n_test"}],
                    "filters": [
                        {
                            "type": "onhour",
                            "onhour": 7,
                            "tag": "custodian_downtime",
                            "default_tz": "utc",
                            "opt-out": True,
                            "weekends": False,
                        },
                    ],
                },
                config={"region": "us-west-2"},
                session_factory=session_factory,
            )

            resources = p.run()
            self.assertEqual(len(resources), 1)

    def test_ec2_onhours_no_filter(self):
        session_factory = self.replay_flight_data("test_ec2_onhours_no_filter")

        t = datetime.datetime.now(tz.gettz("America/New_York"))
        t = t.replace(year=2020, month=2, day=11, hour=7, minute=00)

        with mock_datetime_now(t, datetime):
            p = self.load_policy(
                {
                    "name": "ec2-onhours",
                    "resource": "ec2",
                    "query": [{"tag-key": "c7n_test"}],
                    "filters": [
                        {
                            "type": "onhour",
                            "onhour": 7,
                            "tag": "custodian_downtime",
                            "default_tz": "utc",
                            "opt-out": True,
                            "weekends": False,
                            "state-filter": False,
                        },
                    ],
                },
                config={"region": "us-west-2"},
                session_factory=session_factory,
            )

            resources = p.run()
            self.assertEqual(len(resources), 2)


class TestActions(unittest.TestCase):

    def test_action_construction(self):

        self.assertIsInstance(actions.factory("mark", None), tags.Tag)

        self.assertIsInstance(actions.factory("stop", None), ec2.Stop)

        self.assertIsInstance(actions.factory("terminate", None), ec2.Terminate)


class TestModifySecurityGroupsActionSchema(BaseTest):

    def test_remove_dependencies(self):
        policy = {
            "name": "remove-with-no-isolation-or-add",
            "resource": "ec2",
            "actions": [{"type": "modify-security-groups", "remove": "matched"}],
        }
        self.assertRaises(PolicyValidationError, self.load_policy, data=policy, validate=True)

    def test_invalid_remove_params(self):
        # string invalid
        policy = {
            "name": "remove-with-incorrect-param-string",
            "resource": "ec2",
            "actions": [{"type": "modify-security-groups", "remove": "none"}],
        }
        self.assertRaises(PolicyValidationError, self.load_policy, data=policy, validate=True)

        # list - one valid, one invalid
        policy = {
            "name": "remove-with-incorrect-param-list",
            "resource": "ec2",
            "actions": [
                {
                    "type": "modify-security-groups",
                    "remove": ["invalid-sg", "sg-abcd1234"],
                }
            ],
        }
        self.assertRaises(PolicyValidationError, self.load_policy, policy, validate=True)

    def test_valid_add_params(self):
        # string invalid
        policy = {
            "name": "add-with-incorrect-param-string",
            "resource": "ec2",
            "actions": [
                {"type": "modify-security-groups", "add": "none"},
                {
                    "type": "modify-security-groups",
                    "add": ["invalid-sg", "sg-abcd1234"],
                },
            ],
        }
        self.assertTrue(self.load_policy(data=policy, validate=True))

    def test_invalid_isolation_group_params(self):
        policy = {
            "name": "isolation-group-with-incorrect-param-string",
            "resource": "ec2",
            "actions": [{"type": "modify-security-groups", "isolation-group": "none"}],
        }
        self.assertRaises(PolicyValidationError, self.load_policy, data=policy, validate=True)

        # list - one valid, one invalid
        policy = {
            "name": "isolation-group-with-incorrect-param-list",
            "resource": "ec2",
            "actions": [
                {
                    "type": "modify-security-groups",
                    "isolation-group": ["invalid-sg", "sg-abcd1234"],
                }
            ],
        }
        self.assertRaises(PolicyValidationError, self.load_policy, data=policy, validate=True)


class TestModifySecurityGroupAction(BaseTest):

    def test_security_group_type(self):
        # Test conditions:
        #   - running two instances; one with TestProductionInstanceProfile
        #     and one with none
        #   - security group named TEST-PROD-ONLY-SG exists in VPC and is
        #     attached to both test instances
        session_factory = self.replay_flight_data("test_ec2_security_group_filter")

        # Catch on anything that uses the *PROD-ONLY* security groups but isn't in a prod role
        policy = self.load_policy(
            {
                "name": "restrict-sensitive-sg",
                "resource": "ec2",
                "filters": [
                    {
                        "or": [
                            {
                                "and": [
                                    {
                                        "type": "value",
                                        "key": "IamInstanceProfile.Arn",
                                        "value": "(?!.*TestProductionInstanceProfile)(.*)",
                                        "op": "regex",
                                    },
                                    {
                                        "type": "value",
                                        "key": "IamInstanceProfile.Arn",
                                        "value": "not-null",
                                    },
                                ]
                            },
                            {
                                "type": "value",
                                "key": "IamInstanceProfile",
                                "value": "absent",
                            },
                        ]
                    },
                    {
                        "type": "security-group",
                        "key": "GroupName",
                        "value": "(.*PROD-ONLY.*)",
                        "op": "regex",
                    },
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["InstanceId"], "i-0dd3919bc5bac1ea8")

    def test_security_group_modify_groups_action(self):
        # Test conditions:
        #   - running two instances; one with TestProductionInstanceProfile
        #     and one with none
        #   - security group named TEST-PROD-ONLY-SG exists in VPC and is
        #     attached to both test instances
        session_factory = self.replay_flight_data("test_ec2_modify_groups_action")
        client = session_factory().client("ec2")

        default_sg_id = client.describe_security_groups(GroupNames=["default"])[
            "SecurityGroups"][0]["GroupId"]

        # Catch on anything that uses the *PROD-ONLY* security groups but isn't in a prod role
        policy = self.load_policy(
            {
                "name": "remove-sensitive-sg",
                "resource": "ec2",
                "filters": [
                    {
                        "or": [
                            {
                                "and": [
                                    {
                                        "type": "value",
                                        "key": "IamInstanceProfile.Arn",
                                        "value": "(?!.*TestProductionInstanceProfile)(.*)",
                                        "op": "regex",
                                    },
                                    {
                                        "type": "value",
                                        "key": "IamInstanceProfile.Arn",
                                        "value": "not-null",
                                    },
                                ]
                            },
                            {
                                "type": "value",
                                "key": "IamInstanceProfile",
                                "value": "absent",
                            },
                        ]
                    },
                    {
                        "type": "security-group",
                        "key": "GroupName",
                        "value": "(.*PROD-ONLY.*)",
                        "op": "regex",
                    },
                ],
                "actions": [
                    {
                        "type": "modify-security-groups",
                        "remove": "matched",
                        "isolation-group": default_sg_id,
                    }
                ],
            },
            session_factory=session_factory,
        )
        before_action_resources = policy.run()
        after_action_resources = policy.run()
        self.assertEqual(len(before_action_resources), 1)
        self.assertEqual(
            before_action_resources[0]["InstanceId"], "i-0dd3919bc5bac1ea8"
        )
        self.assertEqual(len(after_action_resources), 0)

    def test_invalid_modify_groups_schema(self):
        policy = {
            "name": "invalid-modify-security-groups-action",
            "resource": "ec2",
            "filters": [],
            "actions": [{"type": "modify-security-groups", "change": "matched"}],
        }
        self.assertRaises(PolicyValidationError, self.load_policy, policy, validate=True)

    def test_ec2_add_security_groups(self):
        # Test conditions:
        #   - running one instance with TestProductionInstanceProfile
        #   - security group named TEST-PROD-ONLY-SG exists in VPC and
        #     is attached to test instance
        #   - security group with id sg-8a4b64f7 exists in VPC and is selected
        #     in a policy to be attached
        session_factory = self.replay_flight_data("test_ec2_add_security_groups")
        policy = self.load_policy(
            {
                "name": "add-sg-to-prod-instances",
                "resource": "ec2",
                "filters": [
                    {
                        "type": "value",
                        "key": "IamInstanceProfile.Arn",
                        "value": "(.*TestProductionInstanceProfile)",
                        "op": "regex",
                    }
                ],
                "actions": [{"type": "modify-security-groups", "add": "sg-8a4b64f7"}],
            },
            session_factory=session_factory,
        )

        first_resources = policy.run()
        self.assertEqual(len(first_resources[0]["NetworkInterfaces"][0]["Groups"]), 1)
        policy.validate()
        second_resources = policy.run()
        self.assertEqual(len(second_resources[0]["NetworkInterfaces"][0]["Groups"]), 2)

    def test_add_remove_with_name(self):
        session_factory = self.replay_flight_data(
            "test_ec2_modify_groups_action_with_name")
        policy = self.load_policy({
            "name": "add-remove-sg-with-name",
            "resource": "ec2",
            "query": [
                {'instance-id': "i-094207d64930768dc"}],
            "actions": [
                {"type": "modify-security-groups",
                 "remove": ["launch-wizard-1"],
                 "add": "launch-wizard-2"}]},
            session_factory=session_factory, config={'region': 'us-east-2'})

        resources = policy.run()
        self.assertEqual(len(resources), 1)

        client = session_factory().client('ec2')
        if self.recording:
            time.sleep(3)
        self.assertEqual(
            utils.jmespath_search(
                "Reservations[].Instances[].SecurityGroups[].GroupName",
                client.describe_instances(InstanceIds=["i-094207d64930768dc"])),
            ["launch-wizard-2"])

    def test_ec2_add_by_tag(self):
        session_factory = self.replay_flight_data("test_ec2_add_by_tag")
        policy = self.load_policy({
            "name": "add-remove-sg-with-name",
            "resource": "ec2",
            "query": [
                {'instance-id': "i-08797f38d2e80c9d0"}],
            "actions": [
                {"type": "modify-security-groups",
                 "add-by-tag": {
                      "key": "environment",
                      "values": ["production"]}}]},
            session_factory=session_factory, config={'region': 'us-west-2'}
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('ec2')
        self.assertEqual(
            utils.jmespath_search(
                "Reservations[].Instances[].SecurityGroups[].GroupId",
                client.describe_instances(InstanceIds=["i-08797f38d2e80c9d0"])),
            ['sg-0cba7a01d343d5c65', 'sg-02e14ba7dd2dbe44b', 'sg-0e630ac9094eff5c5'])


class TestAutoRecoverAlarmAction(BaseTest):

    def test_autorecover_alarm(self):
        session_factory = self.replay_flight_data("test_ec2_autorecover_alarm")
        p = self.load_policy(
            {
                "name": "ec2-autorecover-alarm",
                "resource": "ec2",
                "filters": [{"tag:c7n-test": "autorecover-alarm"}],
                "actions": [{"type": "autorecover-alarm"}],
            },
            session_factory=session_factory,
        )

        resources = p.run()

        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]["InstanceId"], "i-0aaaaec4b77188b69")

        try:
            client = session_factory().client("cloudwatch")
            result = client.describe_alarms(
                AlarmNames=["recover-{}".format(resources[0]["InstanceId"])]
            )
            self.assertTrue(result.get("MetricAlarms"))
        except AssertionError:
            self.fail("alarm not found")


class TestFilter(BaseTest):

    def test_not_filter(self):
        # This test is to get coverage for the `not` filter's process_set method
        session_factory = self.replay_flight_data("test_ec2_not_filter")

        policy = self.load_policy(
            {
                "name": "list-ec2-test-not",
                "resource": "ec2",
                "filters": [{"not": [{"InstanceId": "i-036ee05e8c2ca83b3"}]}],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 2)

        policy = self.load_policy(
            {
                "name": "list-ec2-test-not",
                "resource": "ec2",
                "filters": [
                    {
                        "not": [
                            {
                                "or": [
                                    {"InstanceId": "i-036ee05e8c2ca83b3"},
                                    {"InstanceId": "i-03d8207d8285cbf53"},
                                ]
                            }
                        ]
                    }
                ],
            },
            session_factory=session_factory,
        )

        resources = policy.run()
        self.assertEqual(len(resources), 1)


class TestUserData(BaseTest):

    def test_regex_filter(self):
        session_factory = self.replay_flight_data("test_ec2_userdata")
        policy = self.load_policy(
            {
                "name": "ec2_userdata",
                "resource": "ec2",
                'filters': [{'or': [
                    {'type': 'user-data', 'op': 'regex', 'value': '(?smi).*A[KS]IA'}
                ]}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertGreater(len(resources), 0)


class TestLaunchTemplate(BaseTest):

    def test_template_get_resources(self):
        factory = self.replay_flight_data(
            'test_launch_template_get')
        p = self.load_policy({
            'name': 'ec2-reserved',
            'resource': 'aws.launch-template-version'},
            session_factory=factory)
        resources = p.resource_manager.get_resources([
            'lt-00b3b2755218e3fdd'])
        self.assertEqual(len(resources), 4)
        self.assertIn(
            'arn:aws:ec2:us-east-1:644160558196:launch-template/lt-00b3b2755218e3fdd/4',
            p.resource_manager.get_arns(resources)
        )

    def test_launch_template_versions(self):
        factory = self.replay_flight_data('test_launch_template_query')
        p = self.load_policy({
            'name': 'ec2-reserved',
            'resource': 'aws.launch-template-version'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 8)
        self.assertTrue(all(['LaunchTemplateData' in r for r in resources]))

    def test_launch_template_id_not_found(self):
        factory = self.replay_flight_data("test_launch_template_id_not_found")
        good_lt_id = 'lt-0877401c93c294001'
        p = self.load_policy(
            {'name': 'lt-missing', 'resource': 'launch-template-version'},
            session_factory=factory)
        resources = p.resource_manager.get_resources(
            [('lt-0a49586208137d8de', '1'), ('lt-0877401c93c294001', '3')])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['LaunchTemplateId'], good_lt_id)


class TestReservedInstance(BaseTest):

    def test_reserved_instance_query(self):
        factory = self.replay_flight_data('test_ec2_reserved_instance_query')
        p = self.load_policy({
            'name': 'ec2-reserved',
            'resource': 'aws.ec2-reserved'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)


class TestMonitoringInstance(BaseTest):

    def test_monitor_instance(self):
        factory = self.replay_flight_data('test_ec2_monitor_instance')
        p = self.load_policy({
            'name': 'ec2-monitor-instance',
            'resource': 'aws.ec2',
            'filters': [
                {
                    'Monitoring.State': 'disabled'
                }
            ],
            'actions': [
                {
                    'type': 'set-monitoring',
                    'state': 'enable'
                }
            ]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        instance = utils.query_instances(
            factory(), InstanceIds=[resources[0]['InstanceId']]
        )
        self.assertIn(
            instance[0]['Monitoring']['State'].lower(), ["enabled", "pending"]
        )

    def test_unmonitor_instance(self):
        factory = self.replay_flight_data('test_ec2_unmonitor_instance')
        p = self.load_policy({
            'name': 'ec2-unmonitor-instance',
            'resource': 'aws.ec2',
            'filters': [
                {
                    'Monitoring.State': 'enabled'
                }
            ],
            'actions': [
                {
                    'type': 'set-monitoring',
                    'state': 'disable'
                }
            ]
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        instance = utils.query_instances(
            factory(), InstanceIds=[resources[0]['InstanceId']]
        )
        self.assertIn(
            instance[0]['Monitoring']['State'].lower(), ['disabled', 'disabling']
        )


class TestDedicatedHost(BaseTest):

    def test_dedicated_host_query(self):
        factory = self.replay_flight_data('test_ec2_host_query')
        p = self.load_policy({
            'name': 'ec2-dedicated-hosts',
            'resource': 'aws.ec2-host'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 3)


class TestSpotFleetRequest(BaseTest):

    def test_spot_fleet_request_query(self):
        factory = self.replay_flight_data('test_ec2_spot_fleet_request_query')
        p = self.load_policy({
            'name': 'ec2-spot-fleet-request',
            'resource': 'aws.ec2-spot-fleet-request'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_spot_fleet_request_autoscaling_offhours(self):
        session_factory = self.replay_flight_data("test_spot_fleet_request_autoscaling_offhours")

        p = self.load_policy(
            {
                "name": "all-ec2-spot-to-autoscaling",
                "resource": "ec2-spot-fleet-request",
                "filters": [
                ],
                "actions": [
                    {
                        'type': 'resize',
                        'min-capacity': 0,
                        'desired': 0,
                        'save-options-tag': 'OffHoursPrevious',
                        'suspend-scaling': True,
                    }
                ],
            },
            session_factory=session_factory,
        )
        result = p.run()
        self.assertEqual(len(result), 3)

        client = session_factory().client("ec2")
        sfrs = client.describe_spot_fleet_requests(
        )["SpotFleetRequestConfigs"]
        self.assertEqual(len(sfrs), 3)

    def test_spot_fleet_request_autoscaling_onhours(self):
        session_factory = self.replay_flight_data("test_spot_fleet_request_autoscaling_onhours")

        p = self.load_policy(
            {
                "name": "all-ec2-spot-to-autoscaling",
                "resource": "ec2-spot-fleet-request",
                "filters": [
                ],
                "actions": [
                    {
                        'type': 'resize',
                        'restore-options-tag': 'OffHoursPrevious',
                        'restore-scaling': True,
                    }
                ],
            },
            session_factory=session_factory,
        )
        result = p.run()
        self.assertEqual(len(result), 3)

        client = session_factory().client("ec2")
        sfrs = client.describe_spot_fleet_requests(
        )["SpotFleetRequestConfigs"]
        self.assertEqual(len(sfrs), 3)


class TestEc2HasSpecificManagedPolicyFilter(BaseTest):

    def test_ec2_has_specific_managed_policy_filter(self):
        factory = self.replay_flight_data("test_ec2_has_specific_managed_policy")
        p = self.load_policy(
            {
                "name": "ec2-instance-has-admin-policy",
                "resource": "ec2",
                "filters": [
                    {
                        "type": "has-specific-managed-policy",
                        "value": "admin-policy",
                    }
                ],
            },
            config={"region": "us-west-2"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class TestCapacityReservation(BaseTest):

    def test_capacity_reservation_query(self):
        factory = self.replay_flight_data('test_ec2_capacity_reservation_query')
        p = self.load_policy(
                {
                    'name': 'list-ec2-capacity-reservation',
                    'resource': 'aws.ec2-capacity-reservation'
                },
                session_factory=factory,
                config={'region': 'ap-southeast-1'}
            )
        resources = p.run()
        self.assertEqual(len(resources), 2)
