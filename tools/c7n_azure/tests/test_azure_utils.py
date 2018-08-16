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
