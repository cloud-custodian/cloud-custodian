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
from c7n_azure.utils import Math
from c7n_azure.utils import ResourceIdParser
from c7n_azure.utils import StringUtils
from c7n_azure.tags import TagHelper
from c7n_azure.utils import PortsRangeHelper


RESOURCE_ID = (
    "/subscriptions/ea42f556-5106-4743-99b0-c129bfa71a47/resourceGroups/"
    "rgtest/providers/Microsoft.Compute/virtualMachines/nametest")


class UtilsTest(BaseTest):
    def setUp(self):
        super(UtilsTest, self).setUp()

    def test_get_namespace(self):
        self.assertEqual(ResourceIdParser.get_namespace(RESOURCE_ID), "Microsoft.Compute")

    def test_get_resource_group(self):
        self.assertEqual(ResourceIdParser.get_resource_group(RESOURCE_ID), "rgtest")

    def test_get_resource_type(self):
        self.assertEqual(ResourceIdParser.get_resource_type(RESOURCE_ID), "virtualMachines")

    def test_resource_name(self):
        self.assertEqual(ResourceIdParser.get_resource_name(RESOURCE_ID), "nametest")

    def test_math_mean(self):
        self.assertEqual(Math.mean([4, 5, None, 3]), 4)
        self.assertEqual(Math.mean([None]), 0)
        self.assertEqual(Math.mean([3, 4]), 3.5)

    def test_math_sum(self):
        self.assertEqual(Math.sum([4, 5, None, 3]), 12)
        self.assertEqual(Math.sum([None]), 0)
        self.assertEqual(Math.sum([3.5, 4]), 7.5)

    def test_string_utils_equal(self):
        # Case insensitive matches
        self.assertTrue(StringUtils.equal("FOO", "foo"))
        self.assertTrue(StringUtils.equal("fOo", "FoO"))
        self.assertTrue(StringUtils.equal("ABCDEFGH", "abcdefgh"))
        self.assertFalse(StringUtils.equal("Foo", "Bar"))

        # Case sensitive matches
        self.assertFalse(StringUtils.equal("Foo", "foo", False))
        self.assertTrue(StringUtils.equal("foo", "foo", False))
        self.assertTrue(StringUtils.equal("fOo", "fOo", False))
        self.assertFalse(StringUtils.equal("Foo", "Bar"))

        # Strip whitespace matches
        self.assertTrue(StringUtils.equal(" Foo ", "foo"))
        self.assertTrue(StringUtils.equal("Foo", " foo "))
        self.assertTrue(StringUtils.equal(" Foo ", "Foo", False))
        self.assertTrue(StringUtils.equal("Foo", " Foo ", False))

        # Returns false for non string types
        self.assertFalse(StringUtils.equal(1, "foo"))
        self.assertFalse(StringUtils.equal("foo", 1))
        self.assertFalse(StringUtils.equal(True, False))

    def test_get_tag_value(self):
        resource = {'tags': {'tag1': 'value1', 'tAg2': 'VaLuE2', 'TAG3': 'VALUE3'}}

        self.assertEqual(TagHelper.get_tag_value(resource, 'tag1', True), 'value1')
        self.assertEqual(TagHelper.get_tag_value(resource, 'tag2', True), 'VaLuE2')
        self.assertEqual(TagHelper.get_tag_value(resource, 'tag3', True), 'VALUE3')

    def test_get_ports(self):
        self.assertEqual(PortsRangeHelper.get_ports_set_from_string("5, 4-5, 9"), set([4, 5, 9]))
        rule = {'properties': {'destinationPortRange': '10-12'}}
        self.assertEqual(PortsRangeHelper.get_ports_set_from_rule(rule), set([10, 11, 12]))
        rule = {'properties': {'destinationPortRanges': ['80', '10-12']}}
        self.assertEqual(PortsRangeHelper.get_ports_set_from_rule(rule), set([10, 11, 12, 80]))

    def test_validate_ports_string(self):
        self.assertEqual(PortsRangeHelper.validate_ports_string('80'), True)
        self.assertEqual(PortsRangeHelper.validate_ports_string('22-26'), True)
        self.assertEqual(PortsRangeHelper.validate_ports_string('80,22'), True)
        self.assertEqual(PortsRangeHelper.validate_ports_string('80,22-26'), True)
        self.assertEqual(PortsRangeHelper.validate_ports_string('80,22-26,30-34'), True)
        self.assertEqual(PortsRangeHelper.validate_ports_string('65537'), False)
        self.assertEqual(PortsRangeHelper.validate_ports_string('-1'), False)
        self.assertEqual(PortsRangeHelper.validate_ports_string('10-8'), False)
        self.assertEqual(PortsRangeHelper.validate_ports_string('80,30,25-65538'), False)
        self.assertEqual(PortsRangeHelper.validate_ports_string('65536-65537'), False)

    def test_get_ports_strings_from_list(self):
        self.assertEqual(PortsRangeHelper.get_ports_strings_from_list([]),
                         [])
        self.assertEqual(PortsRangeHelper.get_ports_strings_from_list([10, 11]),
                         ['10-11'])
        self.assertEqual(PortsRangeHelper.get_ports_strings_from_list([10, 12, 13, 14]),
                         ['10', '12-14'])
        self.assertEqual(PortsRangeHelper.get_ports_strings_from_list([10, 12, 13, 14, 20, 21, 22]),
                         ['10', '12-14', '20-22'])

    def test_build_ports_dict(self):
        securityRules = [
            {'properties': {'destinationPortRange': '80-84',
                            'priority': 100,
                            'direction': 'Outbound',
                            'access': 'Allow',
                            'protocol': 'TCP'}},
            {'properties': {'destinationPortRange': '85-89',
                            'priority': 110,
                            'direction': 'Outbound',
                            'access': 'Allow',
                            'protocol': 'UDP'}},
            {'properties': {'destinationPortRange': '80-84',
                            'priority': 120,
                            'direction': 'Inbound',
                            'access': 'Deny',
                            'protocol': 'TCP'}},
            {'properties': {'destinationPortRange': '85-89',
                            'priority': 130,
                            'direction': 'Inbound',
                            'access': 'Deny',
                            'protocol': 'UDP'}},
            {'properties': {'destinationPortRange': '80-89',
                            'priority': 140,
                            'direction': 'Inbound',
                            'access': 'Allow',
                            'protocol': '*'}}]
        nsg = {'properties': {'securityRules': securityRules}}

        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Inbound', 'TCP'),
                         {k: k > 84 for k in range(80, 90)})
        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Inbound', 'UDP'),
                         {k: k < 85 for k in range(80, 90)})
        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Inbound', '*'),
                         {k: False for k in range(80, 90)})
        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Outbound', 'TCP'),
                         {k: True for k in range(80, 85)})
        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Outbound', 'UDP'),
                         {k: True for k in range(85, 90)})
        self.assertEqual(PortsRangeHelper.build_ports_dict(nsg, 'Outbound', '*'),
                         {k: True for k in range(80, 90)})

    def test_snake_to_camel(self):
        self.assertEqual(StringUtils.snake_to_camel(""), "")
        self.assertEqual(StringUtils.snake_to_camel("test"), "test")
        self.assertEqual(StringUtils.snake_to_camel("test_abc"), "testAbc")
        self.assertEqual(StringUtils.snake_to_camel("test_abc_def"), "testAbcDef")

    def test_naming_hash(self):
        source = 'Lorem ipsum dolor sit amet'
        source2 = 'amet sit dolor ipsum Lorem'
        self.assertEqual(StringUtils.naming_hash(source), '16aba539')
        self.assertEqual(StringUtils.naming_hash(source, 10), '16aba5393a')
        self.assertNotEqual(StringUtils.naming_hash(source), StringUtils.naming_hash(source2))
