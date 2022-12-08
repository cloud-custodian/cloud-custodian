# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .azure_common import BaseTest
from c7n_azure.utils import RetentionPeriod


class RetentionPeriodTest(BaseTest):

    def test_iso8601_duration_days(self):
        duration = RetentionPeriod.iso8601_duration(23, RetentionPeriod.Units.days)
        self.assertEqual(duration, "P23D")

    def test_iso8601_duration_weeks(self):
        duration = RetentionPeriod.iso8601_duration(12, RetentionPeriod.Units.weeks)
        self.assertEqual(duration, "P12W")

    def test_iso8601_duration_months(self):
        duration = RetentionPeriod.iso8601_duration(7, RetentionPeriod.Units.months)
        self.assertEqual(duration, "P7M")

    def test_iso8601_duration_years(self):
        duration = RetentionPeriod.iso8601_duration(3, RetentionPeriod.Units.years)
        self.assertEqual(duration, "P3Y")

    def test_parse_iso8601_retention_period_days(self):
        duration = "P31D"
        period, unit = RetentionPeriod.parse_iso8601_retention_period(duration)
        self.assertEqual(period, 31)
        self.assertEqual(unit.iso8601_symbol, 'D')

    def test_parse_iso8601_retention_period_weeks(self):
        duration = "P17W"
        period, unit = RetentionPeriod.parse_iso8601_retention_period(duration)
        self.assertEqual(period, 17)
        self.assertEqual(unit.iso8601_symbol, 'W')

    def test_parse_iso8601_retention_period_months(self):
        duration = "P8M"
        period, unit = RetentionPeriod.parse_iso8601_retention_period(duration)
        self.assertEqual(period, 8)
        self.assertEqual(unit.iso8601_symbol, 'M')

    def test_parse_iso8601_retention_period_years(self):
        duration = "P5Y"
        period, unit = RetentionPeriod.parse_iso8601_retention_period(duration)
        self.assertEqual(period, 5)
        self.assertEqual(unit.iso8601_symbol, 'Y')
