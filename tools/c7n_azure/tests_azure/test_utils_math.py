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

    def test_percentile_interpolates_between_ranks(self):
        data = [4, None, 1, 3, 2]
        self.assertEqual(2.5, Math.percentile(data, 50))
        self.assertAlmostEqual(3.85, Math.percentile(data, 95))
        self.assertEqual(4, Math.percentile(data, 100))

    def test_percentile_single_value(self):
        self.assertEqual(7, Math.percentile([7], 99))

    def test_percentile_without_values(self):
        self.assertIsNone(Math.percentile([None, None], 50))
