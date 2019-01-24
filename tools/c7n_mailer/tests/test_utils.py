# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import unittest

from c7n_mailer import utils


class FormatStruct(unittest.TestCase):

    def test_formats_struct(self):
        expected = '{\n  "foo": "bar"\n}'
        actual = utils.format_struct({'foo': 'bar'})
        self.assertEqual(expected, actual)


class ResourceFormat(unittest.TestCase):

    def test_efs(self):
        self.assertEqual(
            utils.resource_format(
                {'Name': 'abc', 'FileSystemId': 'fsid', 'LifeCycleState': 'available'},
                'efs'),
            'name: abc  id: fsid  state: available')

    def test_eip(self):
        self.assertEqual(
            utils.resource_format(
                {'PublicIp': '8.8.8.8', 'Domain': 'vpc', 'AllocationId': 'eipxyz'},
                'network-addr'),
            'ip: 8.8.8.8  id: eipxyz  scope: vpc')

    def test_nat(self):
        self.assertEqual(
            utils.resource_format(
                {'NatGatewayId': 'nat-xyz', 'State': 'available', 'VpcId': 'vpc-123'},
                'nat-gateway'),
            'id: nat-xyz  state: available  vpc: vpc-123')

    def test_igw(self):
        self.assertEqual(
            utils.resource_format(
                {'InternetGatewayId': 'igw-x', 'Attachments': []},
                'internet-gateway'),
            'id: igw-x  attachments: 0')

    def test_alb(self):
        self.assertEqual(
            utils.resource_format(
                {'LoadBalancerArn':
                    'arn:aws:elasticloadbalancing:us-east-1:367930536793:'
                    'loadbalancer/app/dev/1234567890',
                 'AvailabilityZones': [], 'Scheme': 'internal'},
                'app-elb'),
            'arn: arn:aws:elasticloadbalancing:us-east-1:367930536793:'
            'loadbalancer/app/dev/1234567890'
            '  zones: 0  scheme: internal')
