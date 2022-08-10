# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .azure_common import BaseTest
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
