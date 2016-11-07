# Copyright 2016 Capital One Services, LLC
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
import unittest

from dateutil.parser import parse as date_parse

from c7n.reports.csvout import RECORD_TYPE_FORMATTERS
from .common import load_data


class TestEC2Report(unittest.TestCase):
    def setUp(self):
        data = load_data('report.json')
        self.records = data['ec2']['records']
        self.headers = data['ec2']['headers']
        self.rows = data['ec2']['rows']
        for rec in self.records.values():
            rec['CustodianDate'] = date_parse(rec['CustodianDate'])

    def test_csv(self):
        formatter = RECORD_TYPE_FORMATTERS.get("ec2")()
        tests = [
            (['full'], ['full']),
            (['minimal'], ['minimal']),
            (['full', 'minimal'], ['full', 'minimal']),
            (['full', 'duplicate', 'minimal'], ['full', 'minimal']),
            (['full', 'terminated', 'minimal'], ['full', 'minimal'])]
        for rec_ids, row_ids in tests:
            recs = map(lambda x: self.records[x], rec_ids)
            rows = map(lambda x: self.rows[x], row_ids)
            self.assertEqual(formatter.to_csv(recs), rows)

    def test_custom_fields(self):
        """
        Test the ability to include custom fields.
        """
        formatter_class = RECORD_TYPE_FORMATTERS.get("ec2")
        extra_fields = [
            "custom_field=CustomField",
            "missing_field=MissingField",
            "custom_tag=tag:CustomTag",
        ]

        # First do a test with adding custom fields to the normal ones
        formatter = formatter_class(extra_fields=extra_fields)
        recs = [self.records['full']]
        rows = [self.rows['full_custom']]
        self.assertEqual(formatter.to_csv(recs), rows)

        # Then do a test with only having custom fields
        formatter = formatter_class(extra_fields=extra_fields, no_default_fields=True)
        recs = [self.records['full']]
        rows = [self.rows['minimal_custom']]
        self.assertEqual(formatter.to_csv(recs), rows)
        

class TestASGReport(unittest.TestCase):
    def setUp(self):
        data = load_data('report.json')
        self.records = data['asg']['records']
        self.headers = data['asg']['headers']
        self.rows = data['asg']['rows']
        for rec in self.records.values():
            rec['CustodianDate'] = date_parse(rec['CustodianDate'])

    def test_csv(self):
        formatter = RECORD_TYPE_FORMATTERS.get("asg")()
        tests = [
            (['full'], ['full']),
            (['minimal'], ['minimal']),
            (['full', 'minimal'], ['full', 'minimal']),
            (['full', 'duplicate', 'minimal'], ['full', 'minimal'])]
        for rec_ids, row_ids in tests:
            recs = map(lambda x: self.records[x], rec_ids)
            rows = map(lambda x: self.rows[x], row_ids)
            self.assertEqual(formatter.to_csv(recs), rows)
