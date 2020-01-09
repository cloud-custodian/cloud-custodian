# Copyright 2019 Capital One Services, LLC
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

import unittest

from c7n.filters.core import ComparableVersion

V = ComparableVersion


class TestComparingVersions(unittest.TestCase):

    def test_int_comparisons(self):
        self.assertEqual(V('1.2'), V('1.2'))
        self.assertEqual(V('1.2.3'), V('1.2.3'))
        self.assertNotEqual(V('1.3'), V('1.2'))
        self.assertNotEqual(V('1.2.1'), V('1.2'))
        self.assertLess(V('1.2'), V('1.3'))
        self.assertLess(V('1.2'), V('2'))
        self.assertLess(V('1.2.1'), V('1.2.2'))
        self.assertLess(V('1.2'), V('1.2.1'))
        self.assertGreater(V('1.2'), V('1.1'))
        self.assertGreater(V('1.2'), V('1'))
        self.assertGreater(V('1.3.1'), V('1.3.0'))


    def test_string_comparisons(self):
        self.assertEqual(V('1.rc1'), V('1.rc1'))
        self.assertEqual(V('1.2.rc'), V('1.2.rc'))
        self.assertNotEqual(V('1.3'), V('1.3.rc'))
        self.assertNotEqual(V('1.2-rc'), V('1.2-ab'))
        self.assertLess(V('1.ab'), V('1.rc'))
        self.assertLess(V('1.2.a'), V('1.2.ab'))
        self.assertLess(V('1.rc'), V('1.rc.1'))
        self.assertGreater(V('1.N_1'), V('1.N'))
        self.assertGreater(V('1'), V('1.rc'))
        self.assertGreater(V('1.3.rc-2'), V('1.3.rc-1'))

    def test_mixed_basics(self):
        self.assertNotEqual(V('1.2'), V('1.rc'))
        self.assertNotEqual(V('1.3.ab'), V('1.rc.3'))
        self.assertLess(V('1.3.rc'), V('1.3.1'))
        self.assertLess(V('1.3.rc1'), V('1.3.0'))
        self.assertLess(V('1.3.1-rc1'), V('1.3.1'))
        self.assertLess(V('1.3.rc1'), V('1.3'))
        self.assertGreater(V('1.3'), V('1.XYZ'))
        self.assertGreater(V('1.3'), V('1.3-A'))
        self.assertGreater(V('1.3'), V('1.3.rc1'))


    def test_special_cases(self):
        self.assertGreater(V('5.7.mysql_aurora.2.03.2'), V('5.7.12'))
        self.assertLess(V('5.7.mysql_aurora.2.03.2'), V('5.7.mysql_aurora.2.07'))
