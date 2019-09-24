# Copyright 2019 Microsoft Corporation
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


class UtilsMathTest(BaseTest):

    def test_mean_single_value(self):
        data = [10]
        actual = Math.mean(data)
        self.assertEqual(data[0], actual)

    def test_mean_multi_value(self):
        data = [10, 20, 30, 40, 50]
        actual = Math.mean(data)
        self.assertEqual(30, actual)

    def test_mean_multi_value_with_null(self):
        data = [10, 20, None, 30, 40, 50]
        actual = Math.mean(data)
        self.assertEqual(30, actual)

    def test_sum_single_value(self):
        data = [10]
        actual = Math.sum(data)
        self.assertEqual(data[0], actual)

    def test_sum_multi_value(self):
        data = [10, 20, 30, 40, 50]
        actual = Math.sum(data)
        self.assertEqual(150, actual)

    def test_sum_multi_value_with_null(self):
        data = [10, 20, None, 30, 40, 50]
        actual = Math.sum(data)
        self.assertEqual(150, actual)

    def test_min_single_value(self):
        data = [10]
        actual = Math.min(data)
        self.assertEqual(data[0], actual)

    def test_min_multi_value(self):
        data = [10, 20, 30, 40, 50]
        actual = Math.min(data)
        self.assertEqual(10, actual)

    def test_min_multi_value_with_null(self):
        data = [10, 20, None, 30, 40, 50]
        actual = Math.min(data)
        self.assertEqual(10, actual)

    def test_max_single_value(self):
        data = [10]
        actual = Math.max(data)
        self.assertEqual(data[0], actual)

    def test_max_multi_value(self):
        data = [10, 20, 30, 40, 50]
        actual = Math.max(data)
        self.assertEqual(50, actual)

    def test_max_multi_value_with_null(self):
        data = [10, 20, None, 30, 40, 50]
        actual = Math.max(data)
        self.assertEqual(50, actual)
