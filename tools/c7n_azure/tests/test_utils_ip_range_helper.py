# Copyright 2015-2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from azure_common import BaseTest
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
