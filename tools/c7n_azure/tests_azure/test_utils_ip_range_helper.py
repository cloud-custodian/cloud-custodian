# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest

from .azure_common import BaseTest, cassette_name
from c7n_azure.utils import IpRangeHelper
from netaddr import IPRange, IPSet


class IpRangeHelperTest(BaseTest):

    def test_empty(self):
        data = {'whatever': []}
        actual = IpRangeHelper.parse_ip_ranges(data, 'whatever')
        expected = IPSet()
        self.assertEqual(expected, actual)

    def test_absent(self):
        data = {'whatever': []}
        actual = IpRangeHelper.parse_ip_ranges(data, 'nosuch')
        self.assertIsNone(actual)

    def test_parse_range_and_net(self):
        data = {'whatever': ['0.0.0.0-10.10.10.10', '10.20.20.0/24']}
        actual = IpRangeHelper.parse_ip_ranges(data, 'whatever')
        expected = IPSet(IPRange('0.0.0.0', '10.10.10.10')) | \
            IPSet(IPRange('10.20.20.0', '10.20.20.255'))
        self.assertEqual(expected, actual)

    def test_parse_multi_net(self):
        data = {'whatever': ['1.2.2.127/32', '1.2.2.128/25']}
        actual = IpRangeHelper.parse_ip_ranges(data, 'whatever')
        expected = IPSet(IPRange('1.2.2.127', '1.2.2.127')) | \
            IPSet(IPRange('1.2.2.128', '1.2.2.255'))
        self.assertEqual(expected, actual)

    def test_parse_spaces(self):
        data = {'whatever': ['0.0.0.0 - 10.10.10.10', '10.20.20.0 / 24']}
        actual = IpRangeHelper.parse_ip_ranges(data, 'whatever')
        expected = IPSet(IPRange('0.0.0.0', '10.10.10.10')) | \
            IPSet(IPRange('10.20.20.0', '10.20.20.255'))
        self.assertEqual(expected, actual)

    def test_parse_extra_dash(self):
        data = {'whatever': ['0.0.0.0-10.10.10.10-10.10.10.10']}
        with self.assertRaises(Exception) as context:
            IpRangeHelper.parse_ip_ranges(data, 'whatever')
        expected_error = 'Invalid range. Use x.x.x.x-y.y.y.y or x.x.x.x or x.x.x.x/y.'
        self.assertTrue(expected_error in str(context.exception))

    def test_parse_single_ip(self):
        data = {'whatever': ['1.2.2.127']}
        actual = IpRangeHelper.parse_ip_ranges(data, 'whatever')
        expected = IPSet(IPRange('1.2.2.127', '1.2.2.127'))
        self.assertEqual(expected, actual)

    # Service Tag IP lists are dynamic and will always be changing in live tests
    @pytest.mark.skiplive
    @cassette_name('servicetags')
    def test_parse_alias(self):
        data = {'whatever': ['ServiceTags.ApiManagement.WestUS']}
        actual = IpRangeHelper.parse_ip_ranges(data, 'whatever')
        expected = IPSet(['13.64.39.16/32', '40.112.242.148/31', '40.112.243.240/28'])
        self.assertEqual(expected, actual)

    # Service Tag IP lists are dynamic and will always be changing in live tests
    @pytest.mark.skiplive
    @cassette_name('servicetags')
    def test_parse_alias_and_blocks(self):
        data = {'whatever': ['ServiceTags.ApiManagement.WestUS', '1.2.2.127', '1.2.2.128/25']}
        actual = IpRangeHelper.parse_ip_ranges(data, 'whatever')
        expected = IPSet(['13.64.39.16/32', '40.112.242.148/31', '40.112.243.240/28',
                          '1.2.2.127/32', '1.2.2.128/25'])
        self.assertEqual(expected, actual)

    @cassette_name('servicetags')
    def test_parse_alias_invalid(self):
        data = {'whatever': ['ServiceTags.ApiManagement.Invalid', '1.2.2.127', '1.2.2.128/25']}
        actual = IpRangeHelper.parse_ip_ranges(data, 'whatever')
        expected = IPSet(['1.2.2.127/32', '1.2.2.128/25'])
        self.assertEqual(expected, actual)
