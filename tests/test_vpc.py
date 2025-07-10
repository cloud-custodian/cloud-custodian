# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import time
from .common import BaseTest, functional, event_data, load_data
from unittest.mock import MagicMock

from botocore.exceptions import ClientError as BotoClientError
from c7n.exceptions import PolicyValidationError
from c7n.resources.aws import shape_validate
from pytest_terraform import terraform

import pytest
import jmespath
from .zpill import ACCOUNT_ID


@pytest.mark.audited
@terraform('sg_used_cross_ref')
def test_sg_used_cross_ref(test, sg_used_cross_ref):
    aws_region = 'us-west-2'
    factory = test.replay_flight_data('sg_used_cross_ref', region=aws_region)
    p = test.load_policy({
        'name': 'sg_used_cross_ref',
        'resource': 'security-group',
        'filters': ['used']
    }, session_factory=factory)
    unused = p.resource_manager.filters[0]
    test.patch(
        unused,
        'get_scanners',
        lambda: (("sg-perm-refs", unused.get_sg_refs),)
    )
    resources = p.run()
    assert len(resources) == 1
    assert resources[0]['GroupName'] == sg_used_cross_ref[
        'aws_security_group.n2.name']


@terraform('ec2_igw_subnet')
def test_ec2_igw_subnet(test, ec2_igw_subnet):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data('ec2_igw_subnet', region=aws_region)

    p = test.load_policy(
        {
            'name': 'ec2_igw_subnet',
            'resource': 'ec2',
            'filters': [
                {
                    'type': 'subnet',
                    'igw': True,
                    'key': 'SubnetId',
                    'value': 'present',
                },
            ],
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()

    result_instance_ids = set(i['InstanceId'] for i in resources)
    expected_instance_ids = {
        ec2_igw_subnet['aws_instance.public_auto_assigned.id'],
        ec2_igw_subnet['aws_instance.public_primary_interface.id'],
        ec2_igw_subnet['aws_instance.public_secondary_interface.id'],
    }
    assert len(resources) == len(expected_instance_ids)
    assert expected_instance_ids == result_instance_ids


@terraform('ec2_security_group_filter_multi_enis')
def test_ec2_security_group_filter_multi_enis(test, ec2_security_group_filter_multi_enis):
    aws_region = 'us-east-1'
    session_factory = test.replay_flight_data(
        'ec2_security_group_filter_multi_enis', region=aws_region)

    p = test.load_policy(
        {
            'name': 'ec2_security_group_filter_multi_enis',
            'resource': 'ec2',
            'filters': [
                {
                    'type': 'security-group',
                    'key': 'length(IpPermissions[]|[?IpRanges[?CidrIp==`0.0.0.0/0`]])',
                    'op': 'greater-than',
                    'value': 0,
                },
            ],
        },
        session_factory=session_factory,
        config={'region': aws_region},
    )

    resources = p.run()

    result_instance_ids = set(i['InstanceId'] for i in resources)
    expected_instance_ids = {
        ec2_security_group_filter_multi_enis['aws_instance.primary_interface.id'],
        ec2_security_group_filter_multi_enis['aws_instance.secondary_interface.id'],
    }
    assert len(resources) == len(expected_instance_ids)
    assert expected_instance_ids == result_instance_ids


def test_vpc_usage(test):
    factory = test.replay_flight_data(
        'test_vpc_usage_detect_set', region='us-west-1')
    p = test.load_policy({
        'name': 'vpc-usage',
        'resource': 'aws.vpc',
        'filters': [
            {'type': 'vpc-attributes',
             'addressusage': False}],
        'actions': [
            {'type': 'modify',
             'addressusage': True}],
        }, session_factory=factory)
    resources = p.run()
    assert len(resources) == 1
    client = factory().client('ec2')
    result = client.describe_vpc_attribute(
        VpcId=resources[0]['VpcId'],
        Attribute='enableNetworkAddressUsageMetrics')
    assert result['EnableNetworkAddressUsageMetrics']['Value'] is True


def test_vpc_usage_metric(test):
    factory = test.replay_flight_data(
        'test_vpc_usage_metrics', region='us-west-1')
    p = test.load_policy({
        'name': 'vpc-usage',
        'resource': 'aws.vpc',
        'filters': [
            {'type': 'metrics',
             'statistics': 'Maximum',
             'value': 0,
             'op': 'gte',
             'missing-value': 0,
             'days': 2,
             'name': 'NetworkAddressUsage'}
        ]}, session_factory=factory)
    resources = p.run()
    assert resources[0]['VpcId'] == 'vpc-6d20940b'


def test_eni_igw_subnet(test):
    factory = test.replay_flight_data('test_eni_public_subnet')
    p = test.load_policy({
        'name': 'public-eni',
        'resource': 'aws.eni',
        'filters': [
            {'type': 'subnet',
             'key': 'SubnetId',
             'value': 'present',
             'igw': True}
        ]}, session_factory=factory)
    resources = p.run()
    assert len(resources) == 1
    assert resources[0]['NetworkInterfaceId'] == 'eni-0d47bf614f6182182'

def test_eni_nat_subnet(test):
    factory = test.replay_flight_data('test_eni_private_subnet')
    p = test.load_policy({
        'name': 'private-eni',
        'resource': 'aws.eni',
        'filters': [
            {'type': 'subnet',
             'key': 'SubnetId',
             'value': 'present',
             'nat': True}
        ]}, session_factory=factory)
    resources = p.run()
    assert len(resources) == 2
    assert resources[0]['NetworkInterfaceId'] == 'eni-054de8d628e757d05'

@terraform('aws_code_build_vpc')
def test_codebuild_unused(test, aws_code_build_vpc):
    factory = test.replay_flight_data("test_security_group_codebuild_unused")
    p = test.load_policy(
        {"name": "sg-unused", "resource": "security-group", "filters": ["unused"]},
        session_factory=factory,
    )
    unused = p.resource_manager.filters[0]
    test.patch(
        unused,
        'get_scanners',
        lambda: (('codebuild', unused.get_codebuild_sgs),))
    resources = p.run()
    sg_names = [resource['GroupName'] for resource in resources]
    assert 'example2' in sg_names
    assert 'example1' not in sg_names


@terraform('vpc_flow_logs')
def test_vpc_flow_logs(test, vpc_flow_logs):
    factory = test.replay_flight_data("test_vpc_flow_logs")

    vpc_id = vpc_flow_logs['aws_vpc.example_no_flow_log.id']
    p = test.load_policy(
        {
            "name": "net-find",
            "resource": "vpc",
            "filters": [
                {"VpcId": vpc_id},
                "flow-logs"
            ],
        },
        session_factory=factory,
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(resources[0]["VpcId"], vpc_id)

    vpc_id = vpc_flow_logs['aws_vpc.example.id']
    log_destination = vpc_flow_logs['aws_flow_log.example.log_destination']
    p = test.load_policy(
        {
            "name": "net-find",
            "resource": "vpc",
            "filters": [
                {"VpcId": vpc_id},
                {
                    "type": "flow-logs",
                    "enabled": True,
                    "status": "active",
                    "traffic-type": "all",
                    "destination": log_destination,
                },
            ],
        },
        session_factory=factory,
    )

    resources = p.run()
    test.assertEqual(len(resources), 1)


class VpcTest(BaseTest):

    def test_vpc_post_finding(self):
        # reusing extant test data
        factory = self.replay_flight_data('test_vpc_flow_log_s3_dest')
        p = self.load_policy({
            'name': 'post-vpc-finding',
            'resource': 'vpc',
            'actions': [{
                'type': 'post-finding',
                'types': ['Effects/Custodian']}]},
            session_factory=factory)
        resources = p.resource_manager.resources()
        post_finding = p.resource_manager.actions[0]
        formatted = post_finding.format_resource(resources[0])
        self.maxDiff = None
        self.assertEqual(
            formatted,
            {'Details': {
                'AwsEc2Vpc': {
                    'DhcpOptionsId': 'dopt-24ff1940',
                    'State': 'available',
                    'CidrBlockAssociationSet': [{
                        'AssociationId': 'vpc-cidr-assoc-98ba93f0',
                        'CidrBlock': '10.0.42.0/24',
                        'CidrBlockState': 'associated'}]}},
             'Id': 'arn:aws:ec2:us-east-1:644160558196:vpc/vpc-f1516b97',
             'Partition': 'aws',
             'Region': 'us-east-1',
             'Tags': {'Name': 'FancyTestVPC', 'tagfancykey': 'tagfanncyvalue'},
             'Type': 'AwsEc2Vpc'})
        shape_validate(
            formatted['Details']['AwsEc2Vpc'],
            'AwsEc2VpcDetails', 'securityhub')

    def test_flow_logs_s3_destination(self):
        factory = self.replay_flight_data('test_vpc_flow_log_s3_dest')
        p = self.load_policy({
            'name': 'flow-s3',
            'resource': 'vpc',
            'filters': [{
                'type': 'flow-logs',
                'enabled': True,
                'destination': 'arn:aws:s3:::c7n-vpc-flow-logs'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['VpcId'], 'vpc-d2d616b5')

    def test_flow_logs_absent(self):
        # Test that ONLY vpcs with no flow logs are retained
        #
        # 'vpc-4a9ff72e' - has no flow logs
        # 'vpc-d0e386b7' - has flow logs
        factory = self.replay_flight_data("test_vpc_flow_logs_absent")
        session = factory()
        ec2 = session.client("ec2")
        vpc_id = ec2.create_vpc(CidrBlock="10.4.0.0/24")["Vpc"]["VpcId"]
        self.addCleanup(ec2.delete_vpc, VpcId=vpc_id)

        p = self.load_policy(
            {
                "name": "net-find",
                "resource": "vpc",
                "filters": [{"VpcId": vpc_id}, "flow-logs"],
            },
            session_factory=factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VpcId"], vpc_id)

    def test_flow_logs_misconfiguration(self):
        # Validate that each VPC has at least one valid configuration
        #
        # In terms of filters, we then want to flag VPCs for which every
        # flow log configuration has at least one invalid value
        #
        # Here - have 2 vpcs ('vpc-4a9ff72e','vpc-d0e386b7')
        #
        # The first has three flow logs which each have different
        # misconfigured properties The second has one correctly
        # configured flow log, and one where all config is bad
        #
        # Only the first should be returned by the filter

        factory = self.replay_flight_data("test_vpc_flow_logs_misconfigured")

        vpc_id1 = "vpc-4a9ff72e"
        traffic_type = "all"
        log_group = "/aws/lambda/myIOTFunction"
        status = "active"

        p = self.load_policy(
            {
                "name": "net-find",
                "resource": "vpc",
                "filters": [
                    {
                        "not": [
                            {
                                "type": "flow-logs",
                                "enabled": True,
                                "op": "equal",
                                "set-op": "or",
                                "status": status,
                                "traffic-type": traffic_type,
                                "log-group": log_group,
                            }
                        ]
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['VpcId'], vpc_id1)

    def test_eni_vpc_filter(self):
        self.session_factory = self.replay_flight_data("test_eni_vpc_filter")
        p = self.load_policy({
            "name": "ec2-eni-vpc-filter",
            "resource": "eni",
            "filters": [{
                'type': 'vpc',
                'key': 'tag:Name',
                'value': 'FlowLogTest'}]},
            session_factory=self.session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]["VpcId"], "vpc-d2d616b5")

    def test_attributes_filter_all(self):
        self.session_factory = self.replay_flight_data("test_vpc_attributes")
        p = self.load_policy(
            {
                "name": "dns-hostnames-and-support-enabled",
                "resource": "vpc",
                "filters": [
                    {"type": "vpc-attributes",
                     "dnshostnames": True,
                     "dnssupport": True}
                ],
            },
            session_factory=self.session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VpcId"], "vpc-d2d616b5")

    def test_attributes_filter_hostnames(self):
        self.session_factory = self.replay_flight_data("test_vpc_attributes_hostnames")
        p = self.load_policy(
            {
                "name": "dns-hostnames-enabled",
                "resource": "vpc",
                "filters": [{"type": "vpc-attributes", "dnshostnames": True}],
            },
            session_factory=self.session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VpcId"], "vpc-d2d616b5")

    def test_dhcp_options_filter(self):
        session_factory = self.replay_flight_data("test_vpc_dhcp_options")
        p = self.load_policy(
            {
                "name": "c7n-dhcp-options",
                "resource": "vpc",
                "filters": [
                    {
                        "type": "dhcp-options",
                        "ntp-servers": ["128.138.140.44", "128.138.141.172"],
                        "domain-name": "c7n.internal",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual([len(resources), resources[0]["VpcId"]], [1, "vpc-7af45101"])
        self.assertTrue("c7n:DhcpConfiguration" in resources[0])

    def test_vpc_endpoint_filter(self):
        factory = self.replay_flight_data("test_vpc_endpoint_filter")
        p = self.load_policy(
            {
                "name": "vpc-endpoint-filter",
                "resource": "vpc",
                "filters": [
                    {
                        "type": "vpc-endpoint",
                        "key": "ServiceName",
                        "value": "com.amazonaws.us-east-1.s3",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("vpc-072f438c953672ace" in resources[0]["c7n:matched-vpc-endpoint"])

    def test_subnet_endpoint_filter(self):
        factory = self.replay_flight_data("test_subnet_endpoint_filter")
        p = self.load_policy(
            {
                "name": "subnet-endpoint-filter",
                "resource": "subnet",
                "filters": [
                    {
                        "type": "vpc-endpoint",
                        "key": "ServiceName",
                        "value": "com.amazonaws.us-east-1.athena",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertTrue("subnet-068dfbf3f275a6ae8" in resources[0]["c7n:matched-vpc-endpoint"])

    def test_subnet_ip_address_usage_filter(self):
        factory = self.replay_flight_data("test_subnet_ip_address_usage_filter", region="us-east-2")
        p = self.load_policy(
            {
                "name": "subnet-no-ips-used",
                "resource": "aws.subnet",
                "filters": [
                    {
                        "type": "ip-address-usage",
                        "key": "NumberUsed",
                        "value": 0,
                    }
                ],
            },
            session_factory=factory,
            config={"region": "us-east-2"},
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

        p = self.load_policy(
            {
                "name": "subnet-almost-full",
                "resource": "aws.subnet",
                "filters": [
                    {
                        "type": "ip-address-usage",
                        "key": "PercentUsed",
                        "op": "greater-than",
                        "value": 90,
                    }
                ],
            },
            session_factory=factory,
            config={"region": "us-east-2"},
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_endpoint_policy_filter(self):
        factory = self.replay_flight_data("test_endpoint_policy_filter")
        p = self.load_policy(
            {
                "name": "endpoint-policy-filter",
                "resource": "vpc-endpoint",
                "filters": [
                    {
                        "type": "has-statement",
                        "statements": [{
                            "Effect": "Allow",
                            "Action": "*"
                        }],
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue("vpce-011d813b183878b82" in resources[0]["VpcEndpointId"])


class NetworkLocationTest(BaseTest):

    def test_network_location_sg_missing(self):
        self.factory = self.replay_flight_data("test_network_location_sg_missing_loc")
        client = self.factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
            "Subnet"
        ][
            "SubnetId"
        ]
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        sg_id = client.create_security_group(
            GroupName="some-tier", VpcId=vpc_id, Description="for rabbits"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=sg_id)

        nic = client.create_network_interface(
            SubnetId=web_sub_id, Groups=[sg_id, web_sg_id]
        )[
            "NetworkInterface"
        ][
            "NetworkInterfaceId"
        ]
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[nic, web_sg_id, web_sub_id],
            Tags=[{"Key": "Location", "Value": "web"}],
        )

        p = self.load_policy(
            {
                "name": "netloc",
                "resource": "eni",
                "filters": [
                    {"NetworkInterfaceId": nic},
                    {"type": "network-location", "key": "tag:Location"},
                ],
            },
            session_factory=self.factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(
            matched["c7n:NetworkLocation"],
            [
                {
                    "reason": "SecurityGroupLocationAbsent",
                    "security-groups": {sg_id: None, web_sg_id: "web"},
                },
                {
                    "reason": "SecurityGroupMismatch",
                    "security-groups": {sg_id: None},
                    "resource": "web"
                }
            ],
        )

    @functional
    def test_network_location_ignore(self):
        # if we use network-location-with ignore we won't find any resources.

        # Note we're reusing another tests data set, with the exact same
        # resource creation, just altering our policy filter to examine
        # a different parameter on results.
        self.factory = self.replay_flight_data("test_network_location_sg_cardinality")
        client = self.factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
            "Subnet"
        ][
            "SubnetId"
        ]
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        db_sg_id = client.create_security_group(
            GroupName="db-tier", VpcId=vpc_id, Description="for dbs"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=db_sg_id)

        nic = client.create_network_interface(
            SubnetId=web_sub_id, Groups=[web_sg_id, db_sg_id]
        )[
            "NetworkInterface"
        ][
            "NetworkInterfaceId"
        ]
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[web_sg_id, web_sub_id, nic],
            Tags=[{"Key": "Location", "Value": "web"}],
        )
        client.create_tags(
            Resources=[db_sg_id], Tags=[{"Key": "Location", "Value": "db"}]
        )

        p = self.load_policy(
            {
                "name": "netloc",
                "resource": "eni",
                "filters": [
                    {"NetworkInterfaceId": nic},
                    {
                        "type": "network-location",
                        "ignore": [{"GroupName": "db-tier"}],
                        "key": "tag:Location",
                    },
                ],
            },
            session_factory=self.factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @functional
    def test_network_location_sg_cardinality(self):
        self.factory = self.replay_flight_data("test_network_location_sg_cardinality")
        client = self.factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
            "Subnet"
        ][
            "SubnetId"
        ]
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        db_sg_id = client.create_security_group(
            GroupName="db-tier", VpcId=vpc_id, Description="for dbs"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=db_sg_id)

        nic = client.create_network_interface(
            SubnetId=web_sub_id, Groups=[web_sg_id, db_sg_id]
        )[
            "NetworkInterface"
        ][
            "NetworkInterfaceId"
        ]
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[web_sg_id, web_sub_id, nic],
            Tags=[{"Key": "Location", "Value": "web"}],
        )
        client.create_tags(
            Resources=[db_sg_id], Tags=[{"Key": "Location", "Value": "db"}]
        )

        p = self.load_policy(
            {
                "name": "netloc",
                "resource": "eni",
                "filters": [
                    {"NetworkInterfaceId": nic},
                    {"type": "network-location", "key": "tag:Location"},
                ],
            },
            session_factory=self.factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(
            matched["c7n:NetworkLocation"],
            [
                {
                    "reason": "SecurityGroupLocationCardinality",
                    "security-groups": {db_sg_id: "db", web_sg_id: "web"},
                },
                {
                    "reason": "LocationMismatch",
                    "security-groups": {db_sg_id: "db", web_sg_id: "web"},
                    "subnets": {web_sub_id: "web"},
                },
                {
                    "reason": "SecurityGroupMismatch",
                    "resource": "web",
                    "security-groups": {db_sg_id: "db"}
                }]
        )

    @functional
    def test_network_location_resource_missing(self):
        self.factory = self.replay_flight_data("test_network_location_resource_missing")
        client = self.factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
            "Subnet"
        ][
            "SubnetId"
        ]
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        nic = client.create_network_interface(SubnetId=web_sub_id, Groups=[web_sg_id])[
            "NetworkInterface"
        ][
            "NetworkInterfaceId"
        ]
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[web_sg_id, web_sub_id],
            Tags=[{"Key": "Location", "Value": "web"}],
        )

        p = self.load_policy(
            {
                "name": "netloc",
                "resource": "eni",
                "filters": [
                    {"NetworkInterfaceId": nic},
                    {"type": "network-location", "key": "tag:Location"},
                ],
            },
            session_factory=self.factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(
            matched["c7n:NetworkLocation"],
            [
                {"reason": "ResourceLocationAbsent",
                "resource": None},
                {"security-groups": {web_sg_id: "web"},
                "resource": None,
                "reason": "SecurityGroupMismatch"}],
        )

    def test_network_compare_location_resource_missing(self):
        self.factory = self.replay_flight_data("test_network_compare_location_resource_missing")
        p = self.load_policy(
            {
                "name": "compare",
                "resource": "aws.app-elb",
                "filters": [
                    {"type": "network-location", "key": "tag:NetworkLocation",
                     "compare": ["subnet", "security-group"]}
                ],
            },
            session_factory=self.factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(
            matched["c7n:NetworkLocation"],
            [
                {'reason': 'LocationMismatch', 'security-groups': {},
                 'subnets': {'subnet-914763e7': 'Public', 'subnet-efbcccb7': 'Public'}}
            ],
        )

    @functional
    def test_network_location_triple_intersect(self):
        self.factory = self.replay_flight_data("test_network_location_intersection")
        client = self.factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
            "Subnet"
        ][
            "SubnetId"
        ]
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        nic = client.create_network_interface(SubnetId=web_sub_id, Groups=[web_sg_id])[
            "NetworkInterface"
        ][
            "NetworkInterfaceId"
        ]
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[web_sg_id, web_sub_id, nic],
            Tags=[{"Key": "Location", "Value": "web"}],
        )
        p = self.load_policy(
            {
                "name": "netloc",
                "resource": "eni",
                "filters": [
                    {"NetworkInterfaceId": nic},
                    {"type": "network-location", "key": "tag:Location"},
                ],
            },
            session_factory=self.factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @functional
    def test_network_location_match_in_triple_intersect(self):
        self.factory = self.replay_flight_data("test_network_location_match_in_triple_intersect")
        client = self.factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
            "Subnet"
        ][
            "SubnetId"
        ]
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        nic = client.create_network_interface(SubnetId=web_sub_id, Groups=[web_sg_id])[
            "NetworkInterface"
        ][
            "NetworkInterfaceId"
        ]
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[web_sg_id],
            Tags=[{"Key": "Location", "Value": "web1"}],
        )
        client.create_tags(
            Resources=[web_sub_id],
            Tags=[{"Key": "Location", "Value": "web2"}],
        )
        client.create_tags(
            Resources=[nic],
            Tags=[{"Key": "Location", "Value": "web3"}],
        )
        p = self.load_policy(
            {
                "name": "netloc",
                "resource": "eni",
                "filters": [
                    {"NetworkInterfaceId": nic},
                    {"type": "network-location",
                     "key": "tag:Location",
                     "match": "in",
                     "value": ["web1", "web2", "web3"]},
                ],
            },
            session_factory=self.factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @functional
    def test_network_location_match_in_mismatch(self):
        self.factory = self.replay_flight_data("test_network_location_match_in_mismatch")
        client = self.factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
            "Subnet"
        ][
            "SubnetId"
        ]
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        nic = client.create_network_interface(SubnetId=web_sub_id, Groups=[web_sg_id])[
            "NetworkInterface"
        ][
            "NetworkInterfaceId"
        ]
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[web_sg_id, web_sub_id],
            Tags=[{"Key": "Location", "Value": "web"}],
        )
        client.create_tags(
            Resources=[nic],
            Tags=[{"Key": "Location", "Value": "invalid"}],
        )
        p = self.load_policy(
            {
                "name": "netloc",
                "resource": "eni",
                "filters": [
                    {"NetworkInterfaceId": nic},
                    {"type": "network-location",
                     "key": "tag:Location",
                     "match": "in",
                     "value": ["web"]},
                ],
            },
            session_factory=self.factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @functional
    def test_network_location_match_in_mismatch_subnet(self):
        self.factory = self.replay_flight_data("test_network_location_match_in_mismatch_subnet")
        client = self.factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
            "Subnet"
        ][
            "SubnetId"
        ]
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        nic = client.create_network_interface(SubnetId=web_sub_id, Groups=[web_sg_id])[
            "NetworkInterface"
        ][
            "NetworkInterfaceId"
        ]
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[web_sg_id],
            Tags=[{"Key": "Location", "Value": "web1"}],
        )
        client.create_tags(
            Resources=[nic],
            Tags=[{"Key": "Location", "Value": "web2"}],
        )
        client.create_tags(
            Resources=[web_sub_id],
            Tags=[{"Key": "Location", "Value": "invalid"}],
        )
        p = self.load_policy(
            {
                "name": "netloc",
                "resource": "eni",
                "filters": [
                    {"NetworkInterfaceId": nic},
                    {"type": "network-location",
                     "key": "tag:Location",
                     "match": "in",
                     "value": ["web1", "web2"]},
                ],
            },
            session_factory=self.factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @functional
    def test_network_location_match_in_mismatch_sg(self):
        self.factory = self.replay_flight_data("test_network_location_match_in_mismatch_sg")
        client = self.factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
            "Subnet"
        ][
            "SubnetId"
        ]
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        nic = client.create_network_interface(SubnetId=web_sub_id, Groups=[web_sg_id])[
            "NetworkInterface"
        ][
            "NetworkInterfaceId"
        ]
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[web_sub_id],
            Tags=[{"Key": "Location", "Value": "invalid"}],
        )
        client.create_tags(
            Resources=[nic],
            Tags=[{"Key": "Location", "Value": "web1"}],
        )
        client.create_tags(
            Resources=[web_sg_id],
            Tags=[{"Key": "Location", "Value": "web2"}],
        )
        p = self.load_policy(
            {
                "name": "netloc",
                "resource": "eni",
                "filters": [
                    {"NetworkInterfaceId": nic},
                    {"type": "network-location",
                     "key": "tag:Location",
                     "match": "in",
                     "value": ["web1", "web2"]},
                ],
            },
            session_factory=self.factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @functional
    def test_network_location_match_in_subnet_missing_ok(self):
        self.factory = self.replay_flight_data("test_network_location_match_in_subnet_missing_ok")
        client = self.factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
            "Subnet"
        ][
            "SubnetId"
        ]
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        nic = client.create_network_interface(SubnetId=web_sub_id, Groups=[web_sg_id])[
            "NetworkInterface"
        ][
            "NetworkInterfaceId"
        ]
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[nic],
            Tags=[{"Key": "Location", "Value": "web"}],
        )
        p = self.load_policy(
            {
                "name": "netloc",
                "resource": "eni",
                "filters": [
                    {"NetworkInterfaceId": nic},
                    {"type": "network-location",
                     "key": "tag:Location",
                     "match": "in",
                     "value": ["web"]},
                ],
            },
            session_factory=self.factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)


class NetworkAclTest(BaseTest):

    @functional
    def test_s3_cidr_network_acl_present(self):
        factory = self.replay_flight_data("test_network_acl_s3_present")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        p = self.load_policy(
            {
                "name": "nacl-check",
                "resource": "network-acl",
                "filters": [{"VpcId": vpc_id}, {"type": "s3-cidr", "present": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @functional
    def test_s3_cidr_network_acl_not_present(self):
        factory = self.replay_flight_data("test_network_acl_s3_missing")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        acls = client.describe_network_acls(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        )[
            "NetworkAcls"
        ]

        client.delete_network_acl_entry(
            NetworkAclId=acls[0]["NetworkAclId"],
            RuleNumber=acls[0]["Entries"][0]["RuleNumber"],
            Egress=True,
        )

        p = self.load_policy(
            {
                "name": "nacl-check",
                "resource": "network-acl",
                "filters": [{"VpcId": vpc_id}, "s3-cidr"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class TransitGatewayTest(BaseTest):

    def test_tgw_query(self):
        factory = self.replay_flight_data('test_transit_gateway_query')
        p = self.load_policy({
            'name': 'test-tgw',
            'resource': 'transit-gateway'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Description'], 'test')

    def test_tgw_attachment(self):
        factory = self.replay_flight_data('test_transit_gateway_attachment_query')
        p = self.load_policy({
            'name': 'test-tgw-att',
            'resource': 'transit-attachment'}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ResourceId'], 'vpc-f1516b97')

    def test_tgw_attachment_cloudtrail(self):
        factory = self.replay_flight_data('test_transit_gateway_attachment_query_cwe')
        p = self.load_policy(
            {
                "name": "test-tgw-att-cwe",
                "resource": "transit-attachment",
                "mode": {
                    "type": "cloudtrail",
                    "events": [{
                        "event": "DeleteTransitGatewayVpcAttachment",
                        "ids": "requestParameters.DelTGwVpcAttachReq.TransitGatewayAttachmentId",
                        "source": "ec2.amazonaws.com"
                    }]},
            },
            config={'region': 'us-west-2'}, session_factory=factory)
        resources = p.push(event_data("event-transit-gateway-delete-vpc-attachment.json"))
        self.assertEqual(len(resources), 1)


def test_tgw_attachment_metrics_filter(test):
    factory = test.replay_flight_data("test_tgw_attachment_metrics_filter")
    p = test.load_policy(
        {
            "name": "tgw_attachment-idle",
            "resource": "aws.transit-attachment",
            "filters": [
                {
                    "type": "metrics",
                    "name": "BytesIn",
                    "op": "le",
                    "value": 0,
                    "statistics": "Sum",
                    "days": 1
                }
            ],
        },
        session_factory=factory,
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)


class NetworkInterfaceTest(BaseTest):

    def test_and_or_nest(self):
        factory = self.replay_flight_data("test_network_interface_nested_block_filter")

        p = self.load_policy(
            {
                "name": "net-find",
                "resource": "eni",
                "filters": [
                    {
                        "or": [
                            {"SubnetId": "subnet-55061130"},
                            {
                                "and": [
                                    {
                                        "type": "security-group",
                                        "key": "Description",
                                        "value": "for apps",
                                    },
                                    {
                                        "type": "security-group",
                                        "key": "Description",
                                        "value": "i-am-not-here",
                                    },
                                ]
                            },
                        ]
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            [k for k in resources[0] if k.startswith("c7n")], ["c7n:MatchedFilters"]
        )

    def test_interface_detach(self):
        session_factory = self.replay_flight_data("test_network_interface_detach")
        client = session_factory().client("ec2")
        eni = "eni-0605e38e04785b878"
        instance = "i-05fccf7da99ad47f7"

        p = self.load_policy(
            {
                "name": "detach-enis",
                "resource": "eni",
                "filters": [
                    {
                        "type": "value",
                        "key": "NetworkInterfaceId",
                        "value": eni,
                    },
                    {
                        "type": "value",
                        "key": "Attachment.InstanceId",
                        "value": "present",
                    },
                    {
                        "type": "value",
                        "key": "Association.PublicIp",
                        "value": "present",
                    },
                ],
                "actions": [
                    {
                        "type": "detach",
                    }
                ]
            },
            session_factory=session_factory,
        )
        response = client.describe_instances(InstanceIds=[instance])
        self.assertEqual(len(response["Reservations"][0]["Instances"][0]["NetworkInterfaces"]), 2)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(30)
        response = client.describe_instances(InstanceIds=[instance])
        self.assertEqual(len(response["Reservations"][0]["Instances"][0]["NetworkInterfaces"]), 1)

    def test_interface_detach_primary_nic_1(self):
        session_factory = self.replay_flight_data("test_interface_detach_primary_nic_1")
        client = session_factory().client("ec2")
        eni = "eni-007ebb46d3795b43b"
        instance = "i-042c20d5454745bbe"

        p = self.load_policy(
            {
                "name": "detach-enis",
                "resource": "eni",
                "filters": [
                    {
                        "type": "value",
                        "key": "NetworkInterfaceId",
                        "value": eni,
                    },
                    {
                        "type": "value",
                        "key": "Attachment.InstanceId",
                        "value": "present",
                    },
                    {
                        "type": "value",
                        "key": "Association.PublicIp",
                        "value": "present",
                    },
                ],
                "actions": [
                    {
                        "type": "detach",
                    }
                ]
            },
            session_factory=session_factory,
        )
        response = client.describe_instances(InstanceIds=[instance])
        self.assertEqual(len(response["Reservations"][0]["Instances"][0]["NetworkInterfaces"]), 1)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        response = client.describe_instances(InstanceIds=[instance])
        self.assertEqual(len(response["Reservations"][0]["Instances"][0]["NetworkInterfaces"]), 1)

    def test_interface_detach_primary_nic_2(self):
        session_factory = self.replay_flight_data("test_interface_detach_primary_nic_2")
        client = session_factory().client("ec2")

        p = self.load_policy(
            {
                "name": "detach-enis",
                "resource": "eni",
                "filters": [
                    {
                        "type": "value",
                        "key": "Attachment.InstanceId",
                        "value": "present",
                    },
                    {
                        "type": "value",
                        "key": "Association.PublicIp",
                        "value": "present",
                    },
                ],
                "actions": [
                    {
                        "type": "detach",
                    }
                ]
            },
            session_factory=session_factory,
        )
        response = client.describe_instances()
        self.assertEqual(
            len(jmespath.search(
                'Reservations[].Instances[].NetworkInterfaces[].NetworkInterfaceId',
                response)), 3)
        resources = p.run()
        if self.recording:
            time.sleep(30)
        self.assertEqual(len(resources), 3)
        response = client.describe_instances()
        self.assertEqual(
            len(jmespath.search(
                'Reservations[].Instances[].NetworkInterfaces[].NetworkInterfaceId'
                , response)), 2)

    def test_interface_delete(self):
        factory = self.replay_flight_data("test_network_interface_delete")
        client = factory().client("ec2")
        eni = "eni-d834cdcf"

        p = self.load_policy(
            {
                "name": "eni-delete",
                "resource": "eni",
                "filters": [
                    {
                        "type": "value",
                        "key": "NetworkInterfaceId",
                        "value": eni,
                    }
                ],
                "actions": [
                    {
                        "type": "delete",
                    },
                    {
                        # ensure graceful handling of multiple delete attempts
                        "type": "delete",
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        with self.assertRaises(client.exceptions.ClientError) as e:
            client.describe_network_interfaces(NetworkInterfaceIds=[eni])
        self.assertEqual(e.exception.response['Error']['Code'],
            'InvalidNetworkInterfaceID.NotFound')

    @functional
    def test_interface_subnet(self):
        factory = self.replay_flight_data("test_network_interface_filter")

        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        sub_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.4.8.0/24")["Subnet"][
            "SubnetId"
        ]
        self.addCleanup(client.delete_subnet, SubnetId=sub_id)

        sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=sg_id)

        qsg_id = client.create_security_group(
            GroupName="quarantine-group", VpcId=vpc_id, Description="for quarantine"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=qsg_id)

        net = client.create_network_interface(SubnetId=sub_id, Groups=[sg_id])[
            "NetworkInterface"
        ]
        net_id = net["NetworkInterfaceId"]
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=net_id)

        p = self.load_policy(
            {
                "name": "net-find",
                "resource": "eni",
                "filters": [
                    {"type": "subnet", "key": "SubnetId", "value": sub_id},
                    {
                        "or": [
                            {
                                "type": "security-group",
                                "key": "Description",
                                "value": "for apps",
                            },
                            {
                                "type": "security-group",
                                "key": "Description",
                                "value": "i-am-not-here",
                            },
                        ]
                    },
                ],
                "actions": [
                    {
                        "type": "modify-security-groups",
                        "remove": "matched",
                        "isolation-group": qsg_id,
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["NetworkInterfaceId"], net_id)
        self.assertEqual(resources[0]["c7n:matched-security-groups"], [sg_id])
        results = client.describe_network_interfaces(NetworkInterfaceIds=[net_id])[
            "NetworkInterfaces"
        ]
        self.assertEqual([g["GroupId"] for g in results[0]["Groups"]], [qsg_id])


class NetworkAddrTest(BaseTest):

    @staticmethod
    def release_if_still_present(ec2, network_address):
        try:
            ec2.release_address(AllocationId=network_address["AllocationId"])
        except BotoClientError as e:
            # Swallow the condition that the elastic ip wasn't there (meaning the
            # test should have deleted it), re-raise any other boto client error
            if not (
                e.response["Error"]["Code"] == "InvalidAllocationID.NotFound" and
                network_address["AllocationId"] in e.response["Error"]["Message"]
            ):
                raise e

    def assert_policy_released(self, factory, ec2, network_addr, force=False):
        alloc_id = network_addr["AllocationId"]

        p = self.load_policy(
            {
                "name": "release-network-addr",
                "resource": "network-addr",
                "filters": [{"AllocationId": alloc_id}],
                "actions": [{"type": "release", "force": force}],
            },
            session_factory=factory,
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)
        with self.assertRaises(BotoClientError) as e_cm:
            ec2.describe_addresses(AllocationIds=[alloc_id])
        e = e_cm.exception
        self.assertEqual(e.response["Error"]["Code"], "InvalidAllocationID.NotFound")
        self.assertIn(alloc_id, e.response["Error"]["Message"])

    def assert_policy_release_failed(self, factory, ec2, network_addr):
        alloc_id = network_addr["AllocationId"]

        p = self.load_policy(
            {
                "name": "release-network-addr",
                "resource": "network-addr",
                "filters": [{"AllocationId": alloc_id}],
                "actions": [{"type": "release", "force": False}],
            },
            session_factory=factory,
        )

        resources = p.run()

        self.assertEqual(len(resources), 1)
        address_info = ec2.describe_addresses(AllocationIds=[alloc_id])
        self.assertEqual(len(address_info["Addresses"]), 1)
        self.assertEqual(
            address_info["Addresses"][0]["AssociationId"], network_addr["AssociationId"]
        )

    @functional
    def test_release_detached_vpc(self):
        factory = self.replay_flight_data("test_release_detached_vpc")
        session = factory()
        ec2 = session.client("ec2")
        network_addr = ec2.allocate_address(Domain="vpc")
        self.addCleanup(self.release_if_still_present, ec2, network_addr)
        self.assert_policy_released(factory, ec2, network_addr)

    def test_elastic_ip_get_resources(self):
        factory = self.replay_flight_data('test_elasticip_get_resources')
        p = self.load_policy({
            'name': 'get-addresses',
            'resource': 'network-addr'},
            session_factory=factory)
        resources = p.resource_manager.get_resources(['eipalloc-0da931198e499fdb0'])
        self.assertJmes('[0].PrivateIpAddress', resources, '192.168.0.99')

    def test_elasticip_error(self):
        mock_factory = MagicMock()
        mock_factory.region = 'us-east-1'
        mock_factory().client('ec2').release_address.side_effect = BotoClientError(
            {'Error': {'Code': 'xyz'}},
            operation_name='release_address')

        p = self.load_policy(
            {
                "name": "release-network-addr",
                "resource": "network-addr",
                "actions": [{"type": "release", "force": False}],
            },
            session_factory=mock_factory,
        )
        with self.assertRaises(BotoClientError):
            p.resource_manager.actions[0].process([{
                'PublicIp': "52.207.185.218",
                'Domain': 'Vpc',
                'AllocationId': 'eipalloc-bbaf95b2'}])

    def test_elasticip_alias(self):
        try:
            self.load_policy({'name': 'eip', 'resource': 'aws.elastic-ip'}, validate=True)
        except PolicyValidationError:
            raise
            self.fail("elastic ip alias failed")

    def test_release_attached_ec2(self):
        factory = self.replay_flight_data("test_release_attached_ec2")

        session = factory()
        ec2 = session.client("ec2")

        network_addrs = ec2.describe_addresses(AllocationIds=["eipalloc-2da7a824"])
        self.assertEqual(len(network_addrs["Addresses"]), 1)
        self.assertEqual(
            network_addrs["Addresses"][0]["AssociationId"], "eipassoc-e551ce3f"
        )

        self.assert_policy_released(factory, ec2, network_addrs["Addresses"][0], True)

    def test_release_attached_nif(self):
        factory = self.replay_flight_data("test_release_attached_nif")

        session = factory()
        ec2 = session.client("ec2")

        network_addrs = ec2.describe_addresses(AllocationIds=["eipalloc-ebaaa5e2"])
        self.assertEqual(len(network_addrs["Addresses"]), 1)
        self.assertEqual(
            network_addrs["Addresses"][0]["AssociationId"], "eipassoc-8a8d4647"
        )

        self.assert_policy_released(factory, ec2, network_addrs["Addresses"][0], True)

    def test_norelease_attached_nif(self):
        factory = self.replay_flight_data("test_norelease_attached_nif")

        session = factory()
        ec2 = session.client("ec2")

        network_addrs = ec2.describe_addresses(AllocationIds=["eipalloc-983b3391"])
        self.assertEqual(len(network_addrs["Addresses"]), 1)
        self.assertEqual(
            network_addrs["Addresses"][0]["AssociationId"], "eipassoc-eb20eb26"
        )

        self.assert_policy_release_failed(factory, ec2, network_addrs["Addresses"][0])

    def test_eip_shield(self):
        session_factory = self.replay_flight_data("test_eip_shield")
        p = self.load_policy(
            {
                "name": "eip-shield",
                "resource": "network-addr",
                "filters": [
                    {"type": "shield-enabled", "state": False},
                ],
                "actions": ["set-shield"],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_address_disassociate(self):
        session_factory = self.replay_flight_data("test_address_disassociate")
        client = session_factory().client("ec2")
        allocation_id = "eipalloc-02b147389a1522f9d"

        p = self.load_policy(
            {
                "name": "disassociate-network-addr",
                "resource": "network-addr",
                "filters": [
                    {
                        "AllocationId": allocation_id
                    }
                ],
                "actions": [
                    {
                        "type": "disassociate"
                    }
                ]
            },
            session_factory=session_factory,
        )
        pre_response = client.describe_addresses(AllocationIds=[allocation_id])
        self.assertIn("AssociationId", pre_response["Addresses"][0])
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(5)
        post_response = client.describe_addresses(AllocationIds=[allocation_id])
        self.assertNotIn("AssociationId", post_response["Addresses"][0])

    def test_address_disassociate_exception(self):
        session_factory = self.replay_flight_data("test_address_disassociate_exception")
        client = session_factory().client("ec2")
        allocation_id = "eipalloc-064c7be63c6334ade"
        association_id = "eipassoc-0478441923b77b671"

        p = self.load_policy(
            {
                "name": "disassociate-network-addr",
                "resource": "network-addr",
                "filters": [
                    {
                        "AllocationId": allocation_id
                    }
                ],
                "actions": [
                    {
                        "type": "disassociate"
                    }
                ]
            },
            session_factory=session_factory,
        )
        pre_response = client.describe_addresses(AllocationIds=[allocation_id])
        self.assertIn("AssociationId", pre_response["Addresses"][0])
        client.disassociate_address(AssociationId=association_id)
        if self.recording:
            time.sleep(5)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        post_response = client.describe_addresses(AllocationIds=[allocation_id])
        self.assertNotIn("AssociationId", post_response["Addresses"][0])

    def test_eip_used_by(self):
        factory = self.replay_flight_data("test_eip_used_by")
        p = self.load_policy(
            {
                "name": "eip-used-by-ec2",
                "resource": "network-addr",
                "filters": [
                    {
                        "type": "used-by",
                        "resource-type": "ec2"
                    }
                ]
            },
            session_factory=factory, config={'region': 'us-west-2'}
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class RouteTableTest(BaseTest):

    def test_rt_subnet_filter(self):
        factory = self.replay_flight_data("test_rt_subnet_filter")
        p = self.load_policy(
            {
                "name": "subnet-find",
                "resource": "route-table",
                "filters": [
                    {"RouteTableId": "rtb-309e3d5b"},
                    {"type": "subnet", "key": "tag:Name", "value": "Somewhere"},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(resources[0]["c7n:matched-subnets"], ["subnet-389e3d53"])

    def test_rt_route_filter(self):
        factory = self.replay_flight_data("test_rt_route_filter")
        p = self.load_policy(
            {
                "name": "subnet-find",
                "resource": "route-table",
                "filters": [
                    {"RouteTableId": "rtb-309e3d5b"},
                    {
                        "type": "route",
                        "key": "GatewayId",
                        "op": "glob",
                        "value": "igw*",
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(
            resources[0]["c7n:matched-routes"],
            [
                {
                    u"DestinationCidrBlock": "0.0.0.0/0",
                    u"GatewayId": "igw-3d9e3d56",
                    u"Origin": "CreateRoute",
                    u"State": "active",
                }
            ],
        )

    def test_cross_az_nat_gateway_route_filter(self):
        factory = self.replay_flight_data("test_cross_az_nat_gateway_route_filter")
        p = self.load_policy(
            {
                "name": "cross-az-nat-gw-route-filter",
                "resource": "route-table",
                "filters": [
                    {
                        "type": "cross-az-nat-gateway-route"
                    }
                ],
            },
            config={'region': 'us-west-2'},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        assert resources[0]["c7n:nat-az-mismatch"] == {
            'nat-06e9acaa9c0ab8799': {
                'NatGatewayAz': 'us-west-2a',
                'Subnets': {'subnet-01989283067fcc12f': 'us-west-2c'}
            }
        }
        assert resources[1]['c7n:nat-az-mismatch'] == {
            'nat-06e9acaa9c0ab8799': {
                'NatGatewayAz': 'us-west-2a',
                'Subnets': {'subnet-06b85e2b5aac87c58': 'us-west-2b'}
            }
        }


def test_cross_az_nat_gateway_subnet_resolve(test):
    factory = test.replay_flight_data('test_cross_az_nat_gateway_route_filter')
    p = test.load_policy({
        "name": "cross-az-nat-gw-route-filter",
        "resource": "route-table",
        "filters": [{"type": "cross-az-nat-gateway-route"}]},
        session_factory=factory, config={'region': 'us-west-2'},
    )
    cross_nat = p.resource_manager.filters[0]
    tables = p.resource_manager.source.resources({})
    subnets = {
        s['SubnetId']: s for s in
        p.resource_manager.get_resource_manager('aws.subnet').resources()}

    cross_nat.annotate_subnets_table(tables, subnets)

    table_subnets = {}
    for t in tables:
        table_subnets[t['RouteTableId']] = list(
            cross_nat.resolve_subnets(t, subnets.values()))

    assert table_subnets == {
        'rtb-006b59c15032dee2c': ['subnet-03f2787d0dd5a9094'],
        'rtb-0123fa60166cf0a3b': ['subnet-084dae0d9c11bca66'],
        'rtb-02dab232d4d3e7062': ['subnet-0b5bd0c426f2d2833'],
        'rtb-02ddf9ac6ccafbd28': ['subnet-02c40a509d26f8d34'],
        'rtb-036b56057df88bd48': ['subnet-0fba8806c8acb78c9'],
        'rtb-046ba441cf1187b69': ['subnet-059f1e047a5ca7c1f'],
        'rtb-0564036d8c3e1e117': ['subnet-0a57b9d3da96e4364'],
        'rtb-0790946c364d31f08': ['subnet-01989283067fcc12f'],
        'rtb-0ba85f9bc06635600': ['subnet-09e7dd01ed236e50c'],
        'rtb-0c26eee79085b11b4': ['subnet-aabbccddee'],
        'rtb-0da8d0fc8d7c46a45': ['subnet-06b85e2b5aac87c58'],
        'rtb-0e40b5294fd751b38': ['subnet-0845061a295aef2b6'],
        'rtb-0f13aebd1241f7141': ['subnet-0b8f90974afb1a016']
    }


class PeeringConnectionTest(BaseTest):

    def test_peer_cross_account(self):
        factory = self.replay_flight_data("test_peer_cross_account")
        p = self.load_policy(
            {
                "name": "cross-account",
                "resource": "peering-connection",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:CrossAccountViolations"], ["185106417252"])

    def test_peer_missing_route(self):
        # peer from all routes
        factory = self.replay_flight_data("test_peer_miss_route_filter")
        p = self.load_policy(
            {
                "name": "route-miss",
                "resource": "peering-connection",
                "filters": [{"type": "missing-route"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(resources[0]["VpcPeeringConnectionId"], "pcx-36096b5f")

    def test_peer_missing_one_route(self):
        # peer in one route table, with both sides in the same account
        factory = self.replay_flight_data("test_peer_miss_route_filter_one")
        p = self.load_policy(
            {
                "name": "route-miss",
                "resource": "peering-connection",
                "filters": [{"type": "missing-route"}],
            },
            session_factory=factory,
            config=dict(account_id="619193117841"),
        )
        resources = p.run()
        self.assertEqual(resources[0]["VpcPeeringConnectionId"], "pcx-36096b5f")

    def test_peer_missing_not_found(self):
        # peer in all sides in a single account.
        factory = self.replay_flight_data("test_peer_miss_route_filter_not_found")
        p = self.load_policy(
            {
                "name": "route-miss",
                "resource": "peering-connection",
                "filters": [{"type": "missing-route"}],
            },
            session_factory=factory,
            config=dict(account_id="619193117841"),
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)


class SecurityGroupTest(BaseTest):

    def test_id_selector(self):
        p = self.load_policy({"name": "sg", "resource": "security-group"})
        self.assertEqual(
            p.resource_manager.match_ids(
                ["vpc-asdf", "i-asdf3e", "sg-1235a", "sg-4671"]
            ),
            ["sg-1235a", "sg-4671"],
        )

    @functional
    def test_stale(self):
        # setup a multi vpc security group reference, break the ref
        # and look for stale
        factory = self.replay_flight_data("test_security_group_stale")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        vpc2_id = client.create_vpc(CidrBlock="10.5.0.0/16")["Vpc"]["VpcId"]
        peer_id = client.create_vpc_peering_connection(VpcId=vpc_id, PeerVpcId=vpc2_id)[
            "VpcPeeringConnection"
        ][
            "VpcPeeringConnectionId"
        ]
        client.accept_vpc_peering_connection(VpcPeeringConnectionId=peer_id)
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        self.addCleanup(client.delete_vpc, VpcId=vpc2_id)
        self.addCleanup(
            client.delete_vpc_peering_connection, VpcPeeringConnectionId=peer_id
        )
        sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        t_sg_id = client.create_security_group(
            GroupName="db-tier", VpcId=vpc2_id, Description="for apps"
        )[
            "GroupId"
        ]
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 60000,
                    "ToPort": 62000,
                    "UserIdGroupPairs": [
                        {
                            "GroupId": t_sg_id,
                            "VpcId": vpc2_id,
                            "VpcPeeringConnectionId": peer_id,
                        }
                    ],
                }
            ],
        )
        client.delete_security_group(GroupId=t_sg_id)
        p = self.load_policy(
            {"name": "sg-stale", "resource": "security-group", "filters": ["stale"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["GroupId"], sg_id)
        self.assertEqual(
            resources[0]["MatchedIpPermissions"],
            [
                {
                    u"FromPort": 60000,
                    u"IpProtocol": u"tcp",
                    u"ToPort": 62000,
                    u"UserIdGroupPairs": [
                        {
                            u"GroupId": t_sg_id,
                            u"PeeringStatus": u"active",
                            u"VpcId": vpc2_id,
                            u"VpcPeeringConnectionId": peer_id,
                        }
                    ],
                }
            ],
        )

    def test_used_consumer_eni_in_producer(self):
        p = self.load_policy(
            {"name": "sg-used", "resource": "security-group", "filters": ["used"]},
        )
        used = p.resource_manager.filters[0]
        used.nics = load_data('ram-producer-view-consumer-eni.json')['NetworkInterfaces']

        group_enis = used._get_eni_attributes()
        assert set(group_enis) == {'sg-123', 'sg-456', 'sg-789'}

    def test_used(self):
        factory = self.replay_flight_data("test_security_group_used")
        p = self.load_policy(
            {"name": "sg-used", "resource": "security-group", "filters": ["used"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        self.assertEqual(
            {"sg-f9cc4d9f", "sg-0a2cb503a229c31c1", "sg-1c8a186c"},
            {r["GroupId"] for r in resources},
        )
        self.assertIn("amazon-aws", resources[0]["c7n:InstanceOwnerIds"])
        self.assertIn("vpc_endpoint", resources[0]["c7n:InterfaceTypes"])
        self.assertIn("ec2", resources[0]["c7n:InterfaceResourceTypes"])

    def test_unused_ecs(self):
        factory = self.replay_flight_data("test_security_group_ecs_unused")
        p = self.load_policy(
            {'name': 'sg-xyz',
             'source': 'config',
             'query': [
                 {'clause': "resourceId ='sg-0f026884bba48e350'"}],
             'resource': 'security-group',
             'filters': ['unused']},
            session_factory=factory)
        unused = p.resource_manager.filters[0]
        self.patch(
            unused,
            'get_scanners',
            lambda: (('ecs-cwe', unused.get_ecs_cwe_sgs),))
        resources = p.run()
        assert resources == []

    def test_unused_batch(self):
        factory = self.replay_flight_data("test_security_group_batch_unused")
        # 2 security groups in this flight data:
        # * sg-0f026884bba48e351 (used by the compute environment)
        # * sg-e2842c8b (not used -> should be returned as such)
        p = self.load_policy(
            {'name': 'sg-xyz',
             'resource': 'security-group',
             'filters': ['unused']},
            session_factory=factory)
        unused = p.resource_manager.filters[0]
        self.patch(
            unused,
            'get_scanners',
            lambda: (('batch', unused.get_batch_sgs),))
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertNotEqual(resources[0]["GroupId"], "sg-0f026884bba48e351")  # used
        self.assertEqual(resources[0]["GroupId"], "sg-e2842c8b")             # not used

    def test_unused(self):
        factory = self.replay_flight_data("test_security_group_unused")
        p = self.load_policy(
            {"name": "sg-unused", "resource": "security-group", "filters": ["unused"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_match_resource_validator(self):

        try:
            self.load_policy(
                {'name': 'related-sg',
                 'resource': 'elb',
                 'filters': [
                     {'type': 'security-group',
                      'match-resource': True,
                      'key': "tag:Application",
                      'op': 'not-equal',
                      'operator': 'or'}]},
                validate=True)
        except PolicyValidationError:
            self.fail("should pass validation")

    @functional
    def test_only_ports(self):
        factory = self.replay_flight_data("test_security_group_only_ports")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol="tcp",
            FromPort=60000,
            ToPort=62000,
            CidrIp="10.2.0.0/16",
        )
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol="tcp",
            FromPort=61000,
            ToPort=61000,
            CidrIp="10.2.0.0/16",
        )
        p = self.load_policy(
            {
                "name": "sg-find",
                "resource": "security-group",
                "filters": [
                    {"type": "ingress", "OnlyPorts": [61000]}, {"GroupName": "web-tier"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]["MatchedIpPermissions"],
            [
                {
                    u"FromPort": 60000,
                    u"IpProtocol": u"tcp",
                    u"Ipv6Ranges": [],
                    u"IpRanges": [{u"CidrIp": u"10.2.0.0/16"}],
                    u"PrefixListIds": [],
                    u"ToPort": 62000,
                    u"UserIdGroupPairs": [],
                }
            ],
        )

    @functional
    def test_self_reference_once(self):
        factory = self.replay_flight_data("test_security_group_self_reference")
        client = factory().client("ec2")

        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        # Find the ID of the default security group.
        default_sg_id = client.describe_security_groups(
            Filters=[
                {"Name": "vpc-id", "Values": [vpc_id]},
                {"Name": "group-name", "Values": ["default"]},
            ]
        )[
            "SecurityGroups"
        ][
            0
        ][
            "GroupId"
        ]

        sg1_id = client.create_security_group(
            GroupName="sg1", VpcId=vpc_id, Description="SG 1"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=sg1_id)
        client.authorize_security_group_ingress(
            GroupId=sg1_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 80,
                    "ToPort": 80,
                    "UserIdGroupPairs": [
                        {"GroupId": default_sg_id}, {"GroupId": sg1_id}
                    ],
                }
            ],
        )
        client.authorize_security_group_ingress(
            GroupId=sg1_id,
            IpProtocol="tcp",
            FromPort=60000,
            ToPort=62000,
            CidrIp="10.2.0.0/16",
        )
        client.authorize_security_group_ingress(
            GroupId=sg1_id,
            IpProtocol="tcp",
            FromPort=61000,
            ToPort=61000,
            CidrIp="10.2.0.0/16",
        )

        sg2_id = client.create_security_group(
            GroupName="sg2", VpcId=vpc_id, Description="SG 2"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=sg2_id)
        client.authorize_security_group_egress(
            GroupId=sg2_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "UserIdGroupPairs": [{"GroupId": sg1_id}],
                }
            ],
        )

        p = self.load_policy(
            {
                "name": "sg-find0",
                "resource": "security-group",
                "filters": [
                    {"GroupName": "sg1"},
                    {
                        "type": "ingress",
                        "match-operator": "and",
                        "Ports": [80],
                        "SelfReference": False,
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "sg-find1",
                "resource": "security-group",
                "filters": [
                    {"type": "ingress", "SelfReference": True}, {"GroupName": "sg1"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "sg-find2",
                "resource": "security-group",
                "filters": [
                    {"type": "egress", "SelfReference": True}, {"GroupName": "sg2"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @functional
    def test_security_group_delete(self):
        factory = self.replay_flight_data("test_security_group_delete")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]

        def delete_sg():
            try:
                client.delete_security_group(GroupId=sg_id)
            except Exception:
                pass

        self.addCleanup(delete_sg)

        p = self.load_policy(
            {
                "name": "sg-delete",
                "resource": "security-group",
                "filters": [{"GroupId": sg_id}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["GroupId"], sg_id)
        try:
            client.describe_security_groups(GroupIds=[sg_id])
        except Exception:
            pass
        else:
            self.fail("group not deleted")

    @functional
    def test_port_within_range(self):
        factory = self.replay_flight_data("test_security_group_port_in_range")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol="tcp",
            FromPort=60000,
            ToPort=62000,
            CidrIp="10.2.0.0/16",
        )
        p = self.load_policy(
            {
                "name": "sg-find",
                "resource": "security-group",
                "filters": [
                    {"type": "ingress", "IpProtocol": "tcp", "FromPort": 60000},
                    {"GroupName": "web-tier"},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["GroupName"], "web-tier")
        self.assertEqual(
            resources[0]["MatchedIpPermissions"],
            [
                {
                    u"FromPort": 60000,
                    u"IpProtocol": u"tcp",
                    u"Ipv6Ranges": [],
                    u"IpRanges": [{u"CidrIp": u"10.2.0.0/16"}],
                    u"PrefixListIds": [],
                    u"ToPort": 62000,
                    u"UserIdGroupPairs": [],
                }
            ],
        )

    @functional
    def test_ingress_remove(self):
        factory = self.replay_flight_data("test_security_group_ingress_filter")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        sg_id = client.create_security_group(
            GroupName="web-tier", VpcId=vpc_id, Description="for apps"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol="tcp",
            FromPort=0,
            ToPort=62000,
            CidrIp="10.2.0.0/16",
        )
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        p = self.load_policy(
            {
                "name": "sg-find",
                "resource": "security-group",
                "filters": [
                    {"VpcId": vpc_id},
                    {"type": "ingress", "IpProtocol": "tcp", "FromPort": 0},
                    {"GroupName": "web-tier"},
                ],
                "actions": [{"type": "remove-permissions", "ingress": "matched"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["GroupId"], sg_id)
        group_info = client.describe_security_groups(GroupIds=[sg_id])[
            "SecurityGroups"
        ][
            0
        ]
        self.assertEqual(group_info.get("IpPermissions", []), [])

    def test_security_group_post_finding(self):
        # reuse replay
        factory = self.replay_flight_data('test_security_group_perm_cidr_kv')
        p = self.load_policy({
            'name': 'sg-ingress',
            'resource': 'security-group',
            'source': 'config',
            'query': [
                {'clause': "resourceId ='sg-6c7fa917'"}],
            'actions': [{
                'type': 'post-finding',
                'types': ['Effects/Custodian']}]},
            session_factory=factory)
        resources = p.resource_manager.resources()
        post_finding = p.resource_manager.actions[0]
        formatted = post_finding.format_resource(resources[0])
        for k in ('IpPermissions', 'IpPermissionsEgress', 'Tags'):
            formatted['Details']['Other'].pop(k)
        self.assertEqual(
            formatted,
            {'Details': {
                'Other': {
                    'Description': 'default VPC security group',
                    'GroupId': 'sg-6c7fa917',
                    'GroupName': 'default',
                    'OwnerId': '644160558196',
                    'VpcId': 'vpc-d2d616b5',
                    'c7n:resource-type': 'security-group'}},
             'Id': 'arn:aws:ec2:us-east-1:644160558196:security-group/sg-6c7fa917',
             'Partition': 'aws',
             'Region': 'us-east-1',
             'Tags': {'NetworkLocation': 'Private'},
             'Type': 'AwsEc2SecurityGroup'})

    def test_permission_cidr_kv(self):
        factory = self.replay_flight_data('test_security_group_perm_cidr_kv')
        p = self.load_policy({
            'name': 'sg-ingress',
            'resource': 'security-group',
            'source': 'config',
            'filters': [{
                'type': 'egress',
                'Cidr': '0.0.0.0/0',
            }],
            'query': [
                {'clause': "resourceId ='sg-6c7fa917'"},
            ]}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['GroupId'], 'sg-6c7fa917')

    def test_default_vpc(self):
        # preconditions, more than one vpc, each with at least one
        # security group
        factory = self.replay_flight_data("test_security_group_default_vpc_filter")
        p = self.load_policy(
            {
                "name": "sg-test",
                "resource": "security-group",
                "filters": [{"type": "default-vpc"}, {"GroupName": "default"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_config_source(self):
        factory = self.replay_flight_data("test_security_group_config_source")
        p = self.load_policy(
            {
                "name": "sg-test",
                "resource": "security-group",
                "filters": [{"GroupId": "sg-6c7fa917"}],
            },
            session_factory=factory)

        d_resources = p.run()
        self.assertEqual(len(d_resources), 1)
        p = self.load_policy({
            "name": "sg-test",
            "source": "config",
            "resource": "security-group",
            # to match on filter annotation
            "filters": [{"GroupId": "sg-6c7fa917"}],
            "query": [{"clause": "resourceId = 'sg-6c7fa917'"}]},
            session_factory=factory)
        c_resources = p.run()

        self.assertEqual(len(c_resources), 1)
        self.assertEqual(c_resources[0]["GroupId"], "sg-6c7fa917")
        self.maxDiff = None
        self.assertEqual(c_resources[0], d_resources[0])

    def test_config_rule(self):
        factory = self.replay_flight_data("test_security_group_config_rule")
        p = self.load_policy(
            {
                "name": "sg-test",
                "mode": {"type": "config-rule"},
                "resource": "security-group",
                "filters": [{"type": "ingress", "Cidr": {"value": "0.0.0.0/0"}}],
            },
            session_factory=factory,
        )
        mode = p.get_execution_mode()
        event = event_data("event-config-rule-security-group.json")
        resources = mode.run(event, None)
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["GroupId"], "sg-e2fb6999")

    def test_only_ports_ingress(self):
        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [{"type": "ingress", "OnlyPorts": [80]}],
            }
        )
        resources = [
            {
                "Description": "Typical Internet-Facing Security Group",
                "GroupId": "sg-abcd1234",
                "GroupName": "TestInternetSG",
                "IpPermissions": [
                    {
                        "FromPort": 53,
                        "IpProtocol": "tcp",
                        "IpRanges": ["10.0.0.0/8"],
                        "PrefixListIds": [],
                        "ToPort": 53,
                        "UserIdGroupPairs": [],
                    }
                ],
                "IpPermissionsEgress": [],
                "OwnerId": "123456789012",
                "Tags": [
                    {"Key": "Value", "Value": "InternetSecurityGroup"},
                    {"Key": "Key", "Value": "Name"},
                ],
                "VpcId": "vpc-1234abcd",
            }
        ]
        manager = p.load_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 1)

    @functional
    def test_only_ports_and_cidr_ingress(self):
        factory = self.replay_flight_data("test_only_ports_and_cidr_ingress")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="c7n-only-ports-and-cidr-test", VpcId=vpc_id,
            Description="cloud-custodian test SG"
        )["GroupId"]
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol="tcp",
            FromPort=0,
            ToPort=62000,
            CidrIp="10.2.0.0/16",
        )
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol="tcp",
            FromPort=80,
            ToPort=80,
            CidrIp="0.0.0.0/0",
        )
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol="tcp",
            FromPort=1234,
            ToPort=4321,
            CidrIp="0.0.0.0/0",
        )
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol="tcp",
            FromPort=443,
            ToPort=443,
            CidrIp="0.0.0.0/0",
        )
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol="tcp",
            FromPort=8080,
            ToPort=8080,
            CidrIp="0.0.0.0/0",
        )
        p = self.load_policy(
            {
                "name": "sg-find",
                "resource": "security-group",
                "filters": [
                    {"VpcId": vpc_id},
                    {"GroupName": "c7n-only-ports-and-cidr-test"},
                    {
                        "type": "ingress",
                        "OnlyPorts": [80, 443],
                        "Cidr": {"value": "0.0.0.0/0"}
                    }
                ],
                "actions": [
                    {"type": "remove-permissions", "ingress": "matched"}
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["GroupId"], sg_id)
        self.assertEqual(resources[0]['IpPermissions'], [
            {
                u'PrefixListIds': [],
                u'FromPort': 80,
                u'IpRanges': [{u'CidrIp': '0.0.0.0/0'}],
                u'ToPort': 80,
                u'IpProtocol': 'tcp',
                u'UserIdGroupPairs': [],
                u'Ipv6Ranges': []
            },
            {
                u'PrefixListIds': [],
                u'FromPort': 8080,
                u'IpRanges': [{u'CidrIp': '0.0.0.0/0'}],
                u'ToPort': 8080,
                u'IpProtocol': 'tcp',
                u'UserIdGroupPairs': [],
                u'Ipv6Ranges': []
            },
            {
                u'PrefixListIds': [],
                u'FromPort': 0,
                u'IpRanges': [{u'CidrIp': '10.2.0.0/16'}],
                u'ToPort': 62000,
                u'IpProtocol': 'tcp',
                u'UserIdGroupPairs': [],
                u'Ipv6Ranges': []
            },
            {
                u'PrefixListIds': [],
                u'FromPort': 1234,
                u'IpRanges': [{u'CidrIp': '0.0.0.0/0'}],
                u'ToPort': 4321,
                u'IpProtocol': 'tcp',
                u'UserIdGroupPairs': [],
                u'Ipv6Ranges': []
            },
            {
                u'PrefixListIds': [],
                u'FromPort': 443,
                u'IpRanges': [{u'CidrIp': '0.0.0.0/0'}],
                u'ToPort': 443,
                u'IpProtocol': 'tcp',
                u'UserIdGroupPairs': [],
                u'Ipv6Ranges': []
            }
        ])
        self.assertEqual(
            resources[0]['c7n:MatchedFilters'], [u'VpcId', u'GroupName']
        )
        self.assertEqual(
            resources[0]['MatchedIpPermissions'],
            [
                {
                    u'FromPort': 8080,
                    u'IpRanges': [{u'CidrIp': '0.0.0.0/0'}],
                    u'PrefixListIds': [],
                    u'ToPort': 8080,
                    u'IpProtocol': 'tcp',
                    u'UserIdGroupPairs': [],
                    u'Ipv6Ranges': []
                },
                {
                    u'FromPort': 1234,
                    u'IpRanges': [{u'CidrIp': '0.0.0.0/0'}],
                    u'PrefixListIds': [],
                    u'ToPort': 4321,
                    u'IpProtocol': 'tcp',
                    u'UserIdGroupPairs': [],
                    u'Ipv6Ranges': []
                }
            ]
        )
        group_info = client.describe_security_groups(
            GroupIds=[sg_id]
        )["SecurityGroups"][0]
        self.assertEqual(group_info.get("IpPermissions", []), [
            {
                u'PrefixListIds': [],
                u'FromPort': 80,
                u'IpRanges': [{u'CidrIp': '0.0.0.0/0'}],
                u'ToPort': 80,
                u'IpProtocol': 'tcp',
                u'UserIdGroupPairs': [],
                u'Ipv6Ranges': []
            },
            {
                u'PrefixListIds': [],
                u'FromPort': 0,
                u'IpRanges': [{u'CidrIp': '10.2.0.0/16'}],
                u'ToPort': 62000,
                u'IpProtocol': 'tcp',
                u'UserIdGroupPairs': [],
                u'Ipv6Ranges': []
            },
            {
                u'PrefixListIds': [],
                u'FromPort': 443,
                u'IpRanges': [{u'CidrIp': '0.0.0.0/0'}],
                u'ToPort': 443,
                u'IpProtocol': 'tcp',
                u'UserIdGroupPairs': [],
                u'Ipv6Ranges': []
            }
        ])

    def test_multi_attribute_ingress(self):
        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [
                    {"type": "ingress", "Cidr": {"value": "10.0.0.0/8"}, "Ports": [53]}
                ],
            }
        )
        resources = [
            {
                "Description": "Typical Internet-Facing Security Group",
                "GroupId": "sg-abcd1234",
                "GroupName": "TestInternetSG",
                "IpPermissions": [
                    {
                        "FromPort": 53,
                        "IpProtocol": "tcp",
                        "IpRanges": [{"CidrIp": "10.0.0.0/8"}],
                        "PrefixListIds": [],
                        "ToPort": 53,
                        "UserIdGroupPairs": [],
                    }
                ],
                "IpPermissionsEgress": [],
                "OwnerId": "123456789012",
                "Tags": [
                    {"Key": "Value", "Value": "InternetSecurityGroup"},
                    {"Key": "Key", "Value": "Name"},
                ],
                "VpcId": "vpc-1234abcd",
            }
        ]
        manager = p.load_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 1)

    def test_description_ingress(self):
        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [
                    {"type": "ingress",
                     "Description": {
                         "value": "Approved",
                         "op": "not-equal",
                     },
                     "Cidr": {"value": "0.0.0.0/0"}, "Ports": [22]}
                ],
            }
        )

        resources = [{
            "Description": "allows inbound 0.0.0.0/0:22",
            "GroupName": "ssh",
            "IpPermissions": [
                {
                    "FromPort": 22,
                    "IpProtocol": "tcp",
                    "IpRanges": [
                        {
                            "CidrIp": "0.0.0.0/0",
                            "Description": "ssh",
                        }
                    ],
                    "Ipv6Ranges": []
                }
            ],
            "OwnerId": "644160558196",
            "GroupId": "sg-0b090df1c1f95bc13",
            "IpPermissionsEgress": [],
            "VpcId": "vpc-f1516b97"
        }]
        manager = p.load_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 1)

    def test_ports_ingress(self):
        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [{"type": "ingress", "Ports": [53]}],
            }
        )
        resources = [
            {
                "Description": "Typical Internet-Facing Security Group",
                "GroupId": "sg-abcd1234",
                "GroupName": "TestInternetSG",
                "IpPermissions": [
                    {
                        "FromPort": 53,
                        "IpProtocol": "tcp",
                        "IpRanges": ["10.0.0.0/8"],
                        "PrefixListIds": [],
                        "ToPort": 53,
                        "UserIdGroupPairs": [],
                    }
                ],
                "IpPermissionsEgress": [],
                "OwnerId": "123456789012",
                "Tags": [
                    {"Key": "Value", "Value": "InternetSecurityGroup"},
                    {"Key": "Key", "Value": "Name"},
                ],
                "VpcId": "vpc-1234abcd",
            }
        ]
        manager = p.load_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 1)

    def test_self_reference_ingress_false_positives(self):
        resources = [
            {
                "Description": "Typical Security Group",
                "GroupId": "sg-abcd1234",
                "GroupName": "TestSG",
                "IpPermissions": [
                    {
                        "FromPort": 22,
                        "IpProtocol": "tcp",
                        "IpRanges": [],
                        "PrefixListIds": [],
                        "ToPort": 22,
                        "UserIdGroupPairs": [
                            {"UserId": "123456789012", "GroupId": "sg-abcd1234"}
                        ],
                    }
                ],
                "IpPermissionsEgress": [],
                "OwnerId": "123456789012",
                "Tags": [
                    {"Key": "Value", "Value": "TypicalSecurityGroup"},
                    {"Key": "Key", "Value": "Name"},
                ],
                "VpcId": "vpc-1234abcd",
            }
        ]

        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "Ports": [22],
                        "match-operator": "and",
                        "SelfReference": True,
                    }
                ],
            }
        )
        manager = p.load_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 1)

        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "Ports": [22],
                        "match-operator": "and",
                        "SelfReference": False,
                    }
                ],
            }
        )
        manager = p.load_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 0)

        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "Ports": [22],
                        "match-operator": "and",
                        "Cidr": {
                            "value": "0.0.0.0/0", "op": "eq", "value_type": "cidr"
                        },
                    }
                ],
            }
        )
        manager = p.load_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 0)

        resources = [
            {
                "Description": "Typical Security Group",
                "GroupId": "sg-abcd1234",
                "GroupName": "TestSG",
                "IpPermissions": [
                    {
                        "FromPort": 22,
                        "IpProtocol": "tcp",
                        "IpRanges": [
                            {"CidrIp": "10.42.2.0/24"}, {"CidrIp": "10.42.4.0/24"}
                        ],
                        "PrefixListIds": [],
                        "ToPort": 22,
                        "UserIdGroupPairs": [
                            {"UserId": "123456789012", "GroupId": "sg-abcd5678"}
                        ],
                    }
                ],
                "IpPermissionsEgress": [],
                "OwnerId": "123456789012",
                "Tags": [
                    {"Key": "Value", "Value": "TypicalSecurityGroup"},
                    {"Key": "Key", "Value": "Name"},
                ],
                "VpcId": "vpc-1234abcd",
            }
        ]

        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "Ports": [22],
                        "Cidr": {
                            "value": "10.42.4.0/24", "op": "eq", "value_type": "cidr"
                        },
                    }
                ],
            }
        )
        manager = p.load_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 1)

        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "Ports": [22],
                        "match-operator": "and",
                        "Cidr": {
                            "value": "10.42.3.0/24", "op": "eq", "value_type": "cidr"
                        },
                    }
                ],
            }
        )
        manager = p.load_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 0)

        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "Ports": [22],
                        "Cidr": {
                            "value": "10.42.3.0/24", "op": "ne", "value_type": "cidr"
                        },
                    }
                ],
            }
        )
        manager = p.load_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 1)

        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "Ports": [22],
                        "Cidr": {
                            "value": "0.0.0.0/0", "op": "in", "value_type": "cidr"
                        },
                    }
                ],
            }
        )
        manager = p.load_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 1)

    def test_security_group_reference_ingress_filter(self):
        factory = self.replay_flight_data("test_security_group_reference_ingress_filter")
        p = self.load_policy(
            {
                "name": "security_group_reference_ingress_filter",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "SGReferences": {
                            "key": "tag:SampleTagKey",
                            "value": "SampleTagValue",
                            "op": "equal"
                        }
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_security_group_reference_egress_filter(self):
        factory = self.replay_flight_data("test_security_group_reference_egress_filter")
        p = self.load_policy(
            {
                "name": "security_group_reference_egress_filter",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "egress",
                        "SGReferences": {
                            "key": "tag:SampleTagKey",
                            "value": "SampleTagValue",
                            "op": "equal"
                        }
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_egress_ipv6(self):
        p = self.load_policy({
            "name": "ipv6-test",
            "resource": "security-group",
            "filters": [{
                "type": "egress", "CidrV6": {
                    "value": "::/0"}}]
        })

        resource = {
            "IpPermissionsEgress": [
                {
                    "IpProtocol": "-1",
                    "PrefixListIds": [],
                    "IpRanges": [
                        {
                            "CidrIp": "0.0.0.0/0"
                        }
                    ],
                    "UserIdGroupPairs": [],
                    "Ipv6Ranges": [
                        {
                            "CidrIpv6": "::/0"
                        }
                    ]
                }
            ],
            "Description": "default VPC security group",
            "IpPermissions": [
                {
                    "IpProtocol": "-1",
                    "PrefixListIds": [],
                    "IpRanges": [],
                    "UserIdGroupPairs": [
                        {
                            "UserId": "644160558196",
                            "GroupId": "sg-b744bafc"
                        }
                    ],
                    "Ipv6Ranges": []
                }
            ],
            "GroupName": "default",
            "VpcId": "vpc-f8c6d983",
            "OwnerId": "644160558196",
            "GroupId": "sg-b744bafc"
        }
        manager = p.load_resource_manager()
        matched = manager.filter_resources([resource.copy()])
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(matched[0]['MatchedIpPermissionsEgress']), 1)

        # IPv4 and IPv6 matches should both be included in the list
        # of matched permissions
        p = self.load_policy({
            "name": "ipv4-v6-test",
            "resource": "security-group",
            "filters": [{"or": [
                {"type": "egress", "CidrV6": {
                 "value": "::/0"}},
                {"type": "egress", "Cidr": {
                 "value": "0.0.0.0/0"}},
            ]}]
        })
        manager = p.load_resource_manager()
        matched = manager.filter_resources([resource.copy()])
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(matched[0]['MatchedIpPermissionsEgress']), 2)

    def test_permission_expansion(self):
        factory = self.replay_flight_data("test_security_group_perm_expand")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.42.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="allow-some-ingress", VpcId=vpc_id, Description="inbound access"
        )[
            "GroupId"
        ]
        sg2_id = client.create_security_group(
            GroupName="allowed-reference",
            VpcId=vpc_id,
            Description="inbound ref access",
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=sg2_id)
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "10.42.1.0/24"}],
                }
            ],
        )
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "10.42.2.0/24"}],
                }
            ],
        )
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "UserIdGroupPairs": [{"GroupId": sg2_id}],
                }
            ],
        )
        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "Cidr": {
                            "value": "10.42.1.1", "op": "in", "value_type": "cidr"
                        },
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0].get("MatchedIpPermissions", [])), 1)
        self.assertEqual(
            resources[0].get("MatchedIpPermissions", []),
            [
                {
                    u"FromPort": 443,
                    u"IpProtocol": u"tcp",
                    u"Ipv6Ranges": [],
                    u"PrefixListIds": [],
                    u"UserIdGroupPairs": [],
                    u"IpRanges": [{u"CidrIp": u"10.42.1.0/24"}],
                    u"ToPort": 443,
                }
            ],
        )

    @functional
    def test_cidr_ingress(self):
        factory = self.replay_flight_data("test_security_group_cidr_ingress")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.42.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="allow-https-ingress", VpcId=vpc_id, Description="inbound access"
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "10.42.1.0/24"}],
                }
            ],
        )
        p = self.load_policy(
            {
                "name": "ingress-access",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "Cidr": {
                            "value": "10.42.1.239", "op": "in", "value_type": "cidr"
                        },
                    },
                    {
                        "type": "ingress",
                        "SelfReference": False
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0].get("MatchedIpPermissions", [])), 1)

    def test_cidr_ingress_list(self):
        factory = self.replay_flight_data("test_security_group_cidr_ingress_list")
        p = self.load_policy(
            {
                "name": "ingress-access-list",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "Cidr": {
                            "value": ["10.0.0.0/16", "172.0.0.0/16"],
                            "op": "ni", "value_type": "cidr"
                        },
                    }
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["MatchedIpPermissions"][0]['IpRanges'][0]
            ["CidrIp"], "192.0.0.0/32")

        p = self.load_policy(
            {
                "name": "ingress-access-list",
                "resource": "security-group",
                "filters": [
                    {
                        "type": "ingress",
                        "Cidr": {
                            "value": ["192.0.0.0/16", "172.0.0.0/16"],
                            "op": "in", "value_type": "cidr"
                        },
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual(resources[0]["MatchedIpPermissions"][0]['IpRanges'][0]
                ["CidrIp"], "172.0.0.0/32")
        self.assertEqual(resources[1]["MatchedIpPermissions"][0]['IpRanges'][0]
                ["CidrIp"], "192.0.0.0/32")

    @functional
    def test_cidr_size_egress(self):
        factory = self.replay_flight_data("test_security_group_cidr_size")
        client = factory().client("ec2")
        vpc_id = client.create_vpc(CidrBlock="10.42.0.0/16")["Vpc"]["VpcId"]
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="wide-egress",
            VpcId=vpc_id,
            Description="unnecessarily large egress CIDR rule",
        )[
            "GroupId"
        ]
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        client.revoke_security_group_egress(
            GroupId=sg_id,
            IpPermissions=[{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
        )
        client.authorize_security_group_egress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [
                        {"CidrIp": "10.42.0.0/16"}, {"CidrIp": "10.42.1.0/24"}
                    ],
                }
            ],
        )
        p = self.load_policy(
            {
                "name": "wide-egress",
                "resource": "security-group",
                "filters": [
                    {"GroupName": "wide-egress"},
                    {
                        "type": "egress",
                        "Cidr": {"value": 24, "op": "lt", "value_type": "cidr_size"},
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0].get("MatchedIpPermissionsEgress", [])), 1)

        self.assertEqual(
            resources[0]["MatchedIpPermissionsEgress"],
            [
                {
                    u"FromPort": 443,
                    u"IpProtocol": u"tcp",
                    u"Ipv6Ranges": [],
                    u"IpRanges": [{u"CidrIp": u"10.42.0.0/16"}],
                    u"PrefixListIds": [],
                    u"ToPort": 443,
                    u"UserIdGroupPairs": [],
                }
            ],
        )

    def test_egress_validation_error(self):
        self.assertRaises(
            Exception,
            self.load_policy,
            {
                "name": "sg-find2",
                "resource": "security-group",
                "filters": [
                    {"type": "egress", "InvalidKey": True}, {"GroupName": "sg2"}
                ],
            },
        )

    def test_vpc_by_security_group(self):
        factory = self.replay_flight_data("test_vpc_by_security_group")
        p = self.load_policy(
            {
                "name": "vpc-sg",
                "resource": "vpc",
                "filters": [
                    {
                        "type": "security-group",
                        "key": "tag:Name",
                        "value": "FancyTestGroupPublic",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Tags"][0]["Value"], "FancyTestVPC")

    def test_vpc_scenario_2(self):
        factory = self.replay_flight_data("test_vpc_scenario_2")
        p = self.load_policy(
            {
                "name": "vpc-scenario-2",
                "resource": "vpc",
                "filters": [
                    {
                        "type": "subnet",
                        "value_type": "resource_count",
                        "value": 2,
                        "op": "lt"
                    },
                    {
                        "type": "internet-gateway",
                        "value_type": "resource_count",
                        "value": 1,
                        "op": "gte"
                    },
                    {
                        "type": "nat-gateway",
                        "value_type": "resource_count",
                        "value": 1,
                        "op": "gte"
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_vpc_by_subnet(self):
        factory = self.replay_flight_data("test_vpc_scenario_2")
        p = self.load_policy(
            {
                "name": "vpc-subnet",
                "resource": "vpc",
                "filters": [
                    {
                        "type": "subnet",
                        "key": "tag:Name",
                        "value": "Public subnet",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Tags"][0]["Value"], "scenario-2-test")

    def test_vpc_by_internet_gateway(self):
        factory = self.replay_flight_data("test_vpc_scenario_2")
        p = self.load_policy(
            {
                "name": "vpc-internet-gateway",
                "resource": "vpc",
                "filters": [
                    {
                        "type": "internet-gateway",
                        "key": "tag:Name",
                        "value": "Fancy Internet Gateway",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Tags"][0]["Value"], "scenario-2-test")

    def test_vpc_by_nat_gateway(self):
        factory = self.replay_flight_data("test_vpc_scenario_2")
        p = self.load_policy(
            {
                "name": "vpc-nat-gateway",
                "resource": "vpc",
                "filters": [
                    {
                        "type": "nat-gateway",
                        "key": "tag:Name",
                        "value": "Fancy NAT Gateway",
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Tags"][0]["Value"], "scenario-2-test")


class EndpointTest(BaseTest):

    def test_endpoint_subnet(self):
        factory = self.replay_flight_data("test_vpce_subnet_filter")
        p = self.load_policy(
            {
                "name": "endpoint-subnet",
                "resource": "vpc-endpoint",
                "filters": [
                    {"VpcEndpointType": "Interface"},
                    {"type": "subnet", "key": "tag:Name", "value": "Pluto"},
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:matched-subnets"], ["subnet-914763e7"])

    def test_endpoint_sg(self):
        factory = self.replay_flight_data("test_vpce_sg_filter")
        p = self.load_policy(
            {
                "name": "endpoint-subnet",
                "resource": "vpc-endpoint",
                "filters": [
                    {"VpcEndpointType": "Interface"},
                    {
                        "type": "security-group",
                        "key": "tag:c7n-test-tag",
                        "value": "c7n-test-val",
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:matched-security-groups"], ["sg-6c7fa917"])

    def test_endpoint_cross_account(self):
        session_factory = self.replay_flight_data('test_vpce_cross_account')
        p = self.load_policy(
            {
                'name': 'vpc-endpoint-cross-account',
                'resource': 'vpc-endpoint',
                'filters': [
                    {'type': 'cross-account',
                     'whitelist_orgids': ['o-4amkskbcf1']}
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        violations = resources[0]['c7n:CrossAccountViolations']
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]['Principal'], '*')
        self.assertEqual(violations[0]['Action'], '*')
        self.assertEqual(violations[0]['Resource'], '*')
        self.assertEqual(violations[0]['Effect'], 'Allow')

    def test_set_permission(self):
        session_factory = self.replay_flight_data(
            'test_security_group_set_permissions')
        p = self.load_policy({
            'name': 'security-group',
            'resource': 'aws.security-group',
            'source': 'config',
            'query': [
                {'clause': "resourceId ='sg-04ececeaf1ed666cb'"}],
            'filters': [
                {'type': 'ingress',
                 'Ports': [22],
                 'Cidr': '0.0.0.0/0'}],
            'actions': [
                {'type': 'set-permissions',
                 'remove-egress': [{
                     "IpProtocol": "-1",
                     "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                 }],
                 'remove-ingress': [{
                     'IpProtocol': 'TCP',
                     'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                     'FromPort': 22,
                     'ToPort': 22}],
                 'add-ingress': [
                     # try to add a duplicate, before we remove
                     {'CidrIp': '0.0.0.0/0',
                      'IpProtocol': 'TCP',
                      'FromPort': 22,
                      'ToPort': 22},
                     {'IpPermissions': [{
                         'IpProtocol': 'TCP',
                         'FromPort': 443,
                         'ToPort': 443,
                         'IpRanges': [{
                             'Description': 'SSL To The World',
                             'CidrIp': '0.0.0.0/0'}]
                     }]}]}
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(2)

        client = session_factory().client('ec2')
        group = client.describe_security_groups(
            GroupIds=[resources[0]['GroupId']]).get('SecurityGroups')[0]
        self.assertEqual(group['IpPermissionsEgress'], [])
        self.assertEqual(group['IpPermissions'], [{
            'FromPort': 443,
            'IpProtocol': 'tcp',
            'IpRanges': [{'CidrIp': '0.0.0.0/0',
                          'Description': 'SSL To The World'}],
            'Ipv6Ranges': [],
            'PrefixListIds': [],
            'ToPort': 443,
            'UserIdGroupPairs': []}])
        self.assertEqual(
            p.resource_manager.actions[0].get_permissions(),
            ('ec2:AuthorizeSecurityGroupIngress',
             'ec2:RevokeSecurityGroupIngress',
             'ec2:RevokeSecurityGroupEgress'))


def test_endpoint_metrics_filter(test):
    factory = test.replay_flight_data("test_vpc_endpoint_metrics_filter")
    p = test.load_policy(
        {
            "name": "vpc_endpoint-idle",
            "resource": "aws.vpc-endpoint",
            "filters": [
                {
                    "type": "metrics",
                    "name": "ActiveConnections",
                    "op": "le",
                    "value": 0,
                    "statistics": "Sum",
                    "days": 1
                }
            ],
        },
        session_factory=factory,
    )
    resources = p.run()
    test.assertEqual(len(resources), 0)


class InternetGatewayTest(BaseTest):

    def test_delete_internet_gateways(self):
        factory = self.replay_flight_data("test_internet_gateways_delete")
        p = self.load_policy(
            {
                "name": "delete-internet-gateways",
                "resource": "internet-gateway",
                "filters": [{"tag:Name": "c7n-test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        client = factory(region="us-east-1").client("ec2")
        internet_gateways = client.describe_internet_gateways(
            Filters=[{"Name": "resource-id", "Values": [resources[0]["InternetGatewayId"]]}]
        )[
            "InternetGateways"
        ]
        self.assertFalse(internet_gateways)

    def test_delete_internet_gateways_error(self):
        mock_factory = MagicMock()
        mock_factory.region = 'us-east-1'
        mock_factory().ClientError = (BotoClientError)
        mock_factory().client('ec2').delete_internet_gateway.side_effect = (
            BotoClientError(
                {'Error': {'Code': 'InvalidInternetGatewayId.NotFound'}},
                operation_name='delete_internet_gateway'))
        p = self.load_policy({
            'name': 'delete-internet-gateway',
            'resource': 'internet-gateway',
            "actions": [{"type": "delete"}],
        }, session_factory=mock_factory)

        try:
            p.resource_manager.actions[0].process(
                [{'InternetGatewayId': 'abc'}])
        except BotoClientError:
            self.fail('should not raise')
        mock_factory().client('ec2').delete_internet_gateway.assert_called_once()

    def test_delete_internet_gateway_with_dependencies(self):
        factory = self.replay_flight_data(
            "test_internet_gateway_delete_with_dependencies",
            region="us-east-2"
        )
        p = self.load_policy(
            {
                "name": "delete-internet-gateway-with-dependencies",
                "resource": "internet-gateway",
                "filters": [{"tag:Name": "dev"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory,
            config={"region": "us-east-2"},
        )
        with self.capture_logging("custodian.actions", level=logging.WARNING) as log_output:
            resources = p.run()
            self.assertEqual(len(resources), 1)
            self.assertRegex(log_output.getvalue(), "DependencyViolation error")


class NATGatewayTest(BaseTest):

    def test_query_nat_gateways(self):
        factory = self.replay_flight_data("test_nat_gateways_query")
        p = self.load_policy(
            {"name": "get-nat-gateways", "resource": "nat-gateway"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["State"], "available")

    def test_tag_nat_gateways(self):
        factory = self.replay_flight_data("test_nat_gateways_tag")
        p = self.load_policy(
            {
                "name": "tag-nat-gateways",
                "resource": "nat-gateway",
                "filters": [{"tag:Name": "c7n_test"}],
                "actions": [{"type": "tag", "key": "xyz", "value": "hello world"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "get-nat-gateways",
                "resource": "nat-gateway",
                "filters": [{"tag:xyz": "hello world"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_delete_nat_gateways(self):
        factory = self.replay_flight_data("test_nat_gateways_delete")
        p = self.load_policy(
            {
                "name": "delete-nat-gateways",
                "resource": "nat-gateway",
                "filters": [{"tag:Name": "c7n_test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_nat_gateways_metrics_filter(self):
        factory = self.replay_flight_data("test_nat_gateways_metrics_filter")
        p = self.load_policy(
            {
                "name": "nat-gateways-no-connections",
                "resource": "nat-gateway",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "ActiveConnectionCount",
                        "op": "lt",
                        "value": 100,
                        "statistics": "Sum",
                        "days": 1
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

        p1 = self.load_policy(
            {
                "name": "nat-gateways-no-connections",
                "resource": "nat-gateway",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "ActiveConnectionCount",
                        "op": "gt",
                        "value": 100,
                        "statistics": "Sum",
                        "days": 1
                    }
                ],
            },
            session_factory=factory,
        )
        resources = p1.run()
        self.assertEqual(len(resources), 1)


class FlowLogsTest(BaseTest):

    def test_vpc_create_flow_logs(self):
        session_factory = self.replay_flight_data("test_vpc_create_flow_logs")
        # creates log group
        p = self.load_policy(
            {
                "name": "c7n-create-vpc-flow-logs",
                "resource": "vpc",
                "filters": [
                    {"tag:Name": "FlowLogTest"},
                    {"type": "flow-logs", "enabled": False}
                ],
                "actions": [
                    {
                        "type": "set-flow-log",
                        "DeliverLogsPermissionArn": "arn:aws:iam::644160558196:role/flowlogsRole",
                        "LogGroupName": "/custodian/vpc_log/",
                        "TrafficType": "ALL",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VpcId"], "vpc-d2d616b5")
        client = session_factory(region="us-east-1").client("ec2")
        logs = client.describe_flow_logs(
            Filters=[{"Name": "resource-id", "Values": [resources[0]["VpcId"]]}]
        )["FlowLogs"]
        self.assertEqual(logs[0]["ResourceId"], resources[0]["VpcId"])
        # p1 has same log group name
        p1 = self.load_policy(
            {
                "name": "c7n-create-vpc-flow-logs",
                "resource": "vpc",
                "filters": [
                    {"tag:Name": "testing-vpc"},
                    {"type": "flow-logs", "enabled": False}
                ],
                "actions": [
                    {
                        "type": "set-flow-log",
                        "DeliverLogsPermissionArn": "arn:aws:iam::644160558196:role/flowlogsRole",
                        "LogGroupName": "/custodian/vpc_log/",
                        "TrafficType": "ALL",
                    }
                ],
            },
            session_factory=session_factory,
        )
        res = p1.run()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["VpcId"], "vpc-03005fb9b8740263d")
        client = session_factory(region="us-east-1").client("ec2")
        lgs = client.describe_flow_logs(
            Filters=[{"Name": "resource-id", "Values": [res[0]["VpcId"]]}]
        )["FlowLogs"]
        self.assertEqual(lgs[0]["ResourceId"], res[0]["VpcId"])

    def test_vpc_flow_log_destination(self):
        session_factory = self.replay_flight_data('test_vpc_flow_filter_destination')
        p = self.load_policy(
            {'name': 'c7n-flow-log-s3',
             'resource': 'vpc',
             'filters': [{
                 'type': 'flow-logs',
                 'enabled': True,
                 'destination-type': 's3',
                 'deliver-status': 'success'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:flow-logs'][0]['LogDestination'],
                         'arn:aws:s3:::c7n-vpc-flow-logs')

    def test_vpc_set_flow_logs_s3(self):
        session_factory = self.replay_flight_data("test_vpc_set_flow_logs_s3")
        p = self.load_policy(
            {
                "name": "c7n-vpc-flow-logs-s3",
                "resource": "vpc",
                "filters": [
                    {"tag:Name": "FlowLogTest"}, {"type": "flow-logs", "enabled": False}
                ],
                "actions": [
                    {
                        "type": "set-flow-log",
                        "LogDestinationType": "s3",
                        "LogDestination": "arn:aws:s3:::c7n-vpc-flow-logs/test.log.gz",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VpcId"], "vpc-d2d616b5")
        client = session_factory(region="us-east-1").client("ec2")
        logs = client.describe_flow_logs(
            Filters=[{"Name": "resource-id", "Values": [resources[0]["VpcId"]]}]
        )[
            "FlowLogs"
        ]
        self.assertEqual(logs[0]["ResourceId"], resources[0]["VpcId"])

    def test_vpc_set_flow_logs_legacy_schema_handling(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "c7n-vpc-flow-logs-legacy-schema",
                "resource": "aws.vpc",
                "filters": [
                    {"tag:Name": "FlowLogTest"}, {"type": "flow-logs", "enabled": False}
                ],
                "actions": [
                    {
                        "type": "set-flow-log",
                        "LogDestinationType": "s3",
                        "LogDestination": "arn:aws:s3:::nonsense",
                        "TrafficType": "ALL",
                        "attrs": {
                            "LogDestinationType": "s3",
                            "LogDestination": "arn:aws:s3:::c7n-test/test.log.gz",
                            "TrafficType": "ALL",
                            "TagSpecifications": [
                                {
                                    "ResourceType": "vpc-flow-log",
                                    "Tags": [
                                        {
                                            "Key": "Name",
                                            "Value": "FlowLogTest"
                                        },
                                    ]
                                }
                            ]
                        }
                    }
                ],
            },
            session_factory=None
        )

    def test_vpc_delete_flow_logs(self):
        session_factory = self.replay_flight_data("test_vpc_delete_flow_logs")
        p = self.load_policy(
            {
                "name": "c7n-delete-vpc-flow-logs",
                "resource": "aws.vpc",
                "filters": [
                    {
                        "tag:Name": "FlowLogTest"
                    },
                    {
                        "type": "flow-logs",
                        "enabled": True
                    }
                ],
                "actions": [
                    {
                        "type": "set-flow-log",
                        "state": False,
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VpcId"], "vpc-d2d616b5")
        client = session_factory(region="us-east-1").client("ec2")
        logs = client.describe_flow_logs(
            Filters=[{"Name": "resource-id", "Values": [resources[0]["VpcId"]]}]
        )[
            "FlowLogs"
        ]
        self.assertFalse(logs)

    def test_vpc_set_flow_logs_maxaggrinterval(self):
        session_factory = self.replay_flight_data("test_vpc_set_flow_logs_maxaggrinterval")
        p = self.load_policy(
            {
                "name": "c7n-vpc-flow-logs-maxinterval",
                "resource": "vpc",
                "filters": [
                    {'type': 'flow-logs', 'enabled': False}
                ],
                "actions": [
                    {
                        "type": "set-flow-log",
                        "LogDestinationType": "s3",
                        "LogDestination": "arn:aws:s3:::c7n-vpc-flow-logs/test.log.gz",
                        "MaxAggregationInterval": 60,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["VpcId"], "vpc-d2d616b5")
        client = session_factory(region="us-east-1").client("ec2")
        logs = client.describe_flow_logs(
            Filters=[{"Name": "resource-id", "Values": [resources[0]["VpcId"]]}]
        )[
            "FlowLogs"
        ]
        self.assertEqual(logs[0]["MaxAggregationInterval"], 60)


class TestUnusedKeys(BaseTest):
    def test_vpc_unused_keys(self):
        session_factory = self.replay_flight_data("test_vpc_unused_key_delete")
        client = session_factory().client('ec2')
        instances = client.describe_instances(Filters=[
            {
                "Name": 'instance-state-name',
                "Values": [
                    "running"
                ]
            }
        ])
        self.assertEqual(len(instances['Reservations'][0]['Instances']), 1)
        used_key = {instances['Reservations'][0]['Instances'][0]['KeyName']}
        keys = {key['KeyName'] for key in client.describe_key_pairs()['KeyPairs']}
        unused_key = keys - used_key
        self.assertEqual(len(unused_key), 1)
        self.assertNotEqual(unused_key, used_key)
        p = self.load_policy(
            {
                "name": "unused-keys",
                "resource": "aws.key-pair",
                "filters": [
                    {
                        "type": "unused"
                    },
                ],
                "actions": [
                    {
                        "type": "delete"
                    },
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        keys = {key['KeyName'] for key in client.describe_key_pairs()['KeyPairs']}
        self.assertIn(resources[0]['KeyName'], unused_key)
        self.assertNotEqual(unused_key, keys)
        self.assertEqual(used_key, keys)

    def test_unused_keypair_with_asg_launch_templates(self):
        factory = self.replay_flight_data('test_unused_keypair_launch_template')
        p = self.load_policy(
            {"name": "test-unused-keypairs", "resource": "key-pair", "filters": ["unused"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['KeyName'], 'delete')

    def test_unused_keypair_true(self):
        factory = self.replay_flight_data("test_unused_keypair")
        p = self.load_policy(
            {"name": "test-unused-keypairs", "resource": "key-pair", "filters": ["unused"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_unused_keypair_false(self):
        factory = self.replay_flight_data("test_unused_keypair")
        p = self.load_policy(
            {
                "name": "test-unused-keypairs",
                "resource": "key-pair",
                "filters": [{"type": "unused", "state": False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_vpc_unused_key_not_filtered_error(self):
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    "name": "delete-unused-keys",
                    "resource": "aws.key-pair",
                    "actions": [
                        {
                            "type": "delete"
                        },
                    ]
                }
            )
        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    "name": "delete-unused-keys",
                    "resource": "aws.key-pair",
                    "filters": [
                        {
                            "type": "unused",
                            "state": False
                        },
                    ],
                    "actions": [
                        {
                            "type": "delete"
                        },
                    ]
                }
            )


class TestPrefixList(BaseTest):

    def test_prefix_list_query(self):
        factory = self.replay_flight_data("test_prefix_list_query")
        p = self.load_policy(
            {'name': 'prefix-get', 'resource': 'aws.prefix-list'},
            session_factory=factory)
        resources = p.resource_manager.get_resources(
            ["pl-02d12d37020480a5f", "pl-0c79279cd77a6e7c2"])
        assert len(resources) == 2

    def test_prefix_entry(self):
        factory = self.replay_flight_data("test_prefix_list_entry")
        p = self.load_policy(
            {'name': 'prefix-get',
             'resource': 'aws.prefix-list',
             'filters': [
                 {'PrefixListName': 'All VPC CIDR'},
                 {'type': 'entry',
                  'key': 'Cidr',
                  'value': '172.31.2.10/32',
                  'value_type': 'cidr',
                  'op': 'contains'}
             ]},
            session_factory=factory)
        resources = p.run()
        assert 'c7n:matched-entries' in resources[0]
        assert 'c7n:prefix-entries' in resources[0]


class TestModifySubnet(BaseTest):

    def test_subnet_modify_attributes(self):
        session_factory = self.replay_flight_data(
            "test_subnet_modify_attributes")
        client = session_factory().client("ec2")
        p = self.load_policy(
            {
                "name": "turn-on-public-ip-protection",
                "resource": "aws.subnet",
                "filters": [
                    {
                        "type": "value",
                        "key": "MapPublicIpOnLaunch",
                        "value": True,
                    },
                ],
                "actions": [
                    {
                        "type": "modify",
                        "MapPublicIpOnLaunch": False,
                    },
                ],
            },
            session_factory=session_factory)
        resources = p.run()
        ModifiedSubnet = client.describe_subnets(
            SubnetIds=[resources[0]['SubnetId']])
        MapPublicIpOnLaunch = ModifiedSubnet["Subnets"][0]["MapPublicIpOnLaunch"]
        self.assertEqual(MapPublicIpOnLaunch, False)


class TrafficMirror(BaseTest):

    def test_traffic_mirror_session_delete(self):
        session_factory = self.replay_flight_data('test_traffic_mirror_session_delete')
        p = self.load_policy({
            'name': 'traffic-mirror-session-delete',
            'resource': 'mirror-session',
            "filters": [
                {"tag:Owner": "absent"}
            ],
            "actions": [
                {
                    "type": "delete"
                }
            ],
        },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["TrafficMirrorSessionId"], "tms-084dc356a819e99ae")
        client = session_factory(region="us-east-1").client("ec2")
        if self.recording:
            time.sleep(5)
        self.assertEqual(
            client.describe_traffic_mirror_sessions().get('TrafficMirrorSessions'), [])

    def test_traffic_mirror_target(self):
        session_factory = self.replay_flight_data('test_traffic_mirror_target')
        p = self.load_policy({
            'name': 'traffic-mirror-target',
            'resource': 'mirror-target',
            "filters": [
                {"tag:Owner": "present"}
            ],
        },
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["TrafficMirrorTargetId"], "tmt-02cc3955d41358894")
        self.assertEqual(resources[0]['Tags'], [{"Key": "Owner", "Value": "pratyush"}])


@terraform("vpc_delete")
def test_vpc_delete(test, vpc_delete):
    factory = test.replay_flight_data("test_vpc_delete")
    p = test.load_policy(
        {
            "name": "delete-vpc",
            "resource": "vpc",
            "filters": [{"tag:Name": "c7n-test"}],
            "actions": [{"type": "delete-empty"}],
        },
        session_factory=factory,
    )
    resources = p.run()
    test.assertEqual(len(resources), 1)
    client = factory(region="us-east-1").client("ec2")
    vpcs = client.describe_vpcs(
        Filters=[{"Name": "resource-id", "Values": [resources[0]["VpcId"]]}]
    )[
        "Vpcs"
    ]
    test.assertFalse(vpcs)


@terraform("eip_shield_sync")
def test_eip_shield_sync(test, eip_shield_sync):

    session_factory = test.replay_flight_data("test_eip_shield_sync_1")

    shield_client = session_factory().client("shield")

    p = test.load_policy(
        {
            "name": "eip-shield-sync",
            "resource": "network-addr",
            "filters": [
                {"type": "shield-enabled", "state": False},
            ],
            "actions": [{
                "type": "set-shield",
                "state": True,
                "sync": True
            }
            ],
        },
        config={"account_id": ACCOUNT_ID},
        session_factory=session_factory,
    )

    resources = p.run()

    protections = shield_client.list_protections(
        InclusionFilters={"ResourceTypes": ["ELASTIC_IP_ALLOCATION"]}
    )
    for p in protections["Protections"]:
        if eip_shield_sync["aws_eip.unprotected.allocation_id"] in p["ResourceArn"]:
            test.addCleanup(shield_client.delete_protection, ProtectionId=p["Id"])

    test.assertEqual(len(resources), 1)
    test.assertEqual(resources[0]["Tags"][0]["Value"], "unprotected")

    # ensure that there are now 2 EIPs that are shield protected
    protections = shield_client.list_protections(
        InclusionFilters={"ResourceTypes": ["ELASTIC_IP_ALLOCATION"]}
    )
    test.assertEqual(len(protections["Protections"]), 2)


@terraform("eip_shield_sync")
def test_eip_shield_sync_deleted(test, eip_shield_sync):

    session_factory = test.replay_flight_data("test_eip_shield_sync_2")

    shield_client = session_factory().client("shield")
    ec2_client = session_factory().client("ec2")

    # delete the original protected resource
    ec2_client.release_address(AllocationId=eip_shield_sync["aws_eip.protected.allocation_id"])

    p = test.load_policy(
        {
            "name": "eip-shield-sync",
            "resource": "network-addr",
            "filters": [
                {"type": "shield-enabled", "state": False},
            ],
            "actions": [{
                "type": "set-shield",
                "state": True,
                "sync": True
            }
            ],
        },
        config={"account_id": ACCOUNT_ID},
        session_factory=session_factory,
    )

    resources = p.run()

    protections = shield_client.list_protections(
        InclusionFilters={"ResourceTypes": ["ELASTIC_IP_ALLOCATION"]}
    )
    for p in protections["Protections"]:
        if eip_shield_sync["aws_eip.unprotected.allocation_id"] in p["ResourceArn"]:
            test.addCleanup(shield_client.delete_protection, ProtectionId=p["Id"])

    test.assertEqual(len(resources), 1)
    test.assertEqual(resources[0]["Tags"][0]["Value"], "unprotected")

    # ensure that there is only 1 EIP that are shield protected after sync
    protections = shield_client.list_protections(
        InclusionFilters={"ResourceTypes": ["ELASTIC_IP_ALLOCATION"]}
    )
    test.assertEqual(len(protections["Protections"]), 1)


class TestVPCEndpointServiceConfiguration(BaseTest):
    def test_query(self):
        session_factory = self.replay_flight_data("test_vpc_endpoint_service_configuration_query")
        p = self.load_policy({
            "name": "vpc-endpoint-service-configuration-query",
            "resource": "aws.vpc-endpoint-service-configuration",
            "filters": [{
                'RemoteAccessEnabled': False
            }],
        }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ServiceId'], 'vpce-svc-042193297e333714e')
