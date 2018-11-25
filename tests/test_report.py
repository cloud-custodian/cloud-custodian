# Copyright 2015-2017 Capital One Services, LLC
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

from c7n.policy import Policy
from c7n.reports.csvout import Formatter
from .common import Config, load_data


EC2_POLICY = Policy({"name": "report-test-ec2", "resource": "ec2"}, Config.empty())
ASG_POLICY = Policy({"name": "report-test-asg", "resource": "asg"}, Config.empty())
ELB_POLICY = Policy({"name": "report-test-elb", "resource": "elb"}, Config.empty())


class TestEC2Report(unittest.TestCase):

    def setUp(self):
        data = load_data("report.json")
        self.records = data["ec2"]["records"]
        self.headers = data["ec2"]["headers"]
        self.rows = data["ec2"]["rows"]

    def test_csv(self):
        formatter = Formatter(EC2_POLICY.resource_manager.resource_type)
        tests = [
            (["full"], ["full"]),
            (["minimal"], ["minimal"]),
            (["full", "minimal"], ["full", "minimal"]),
            (["full", "duplicate", "minimal"], ["full", "minimal"]),
        ]
        for rec_ids, row_ids in tests:
            recs = list(map(lambda x: self.records[x], rec_ids))
            rows = list(map(lambda x: self.rows[x], row_ids))
            self.assertEqual(formatter.to_csv(recs), rows)

    def test_custom_fields(self):
        # Test the ability to include custom fields.
        extra_fields = [
            "custom_field=CustomField",
            "missing_field=MissingField",
            "custom_tag=tag:CustomTag",
        ]

        # First do a test with adding custom fields to the normal ones
        formatter = Formatter(
            EC2_POLICY.resource_manager.resource_type, extra_fields=extra_fields
        )
        recs = [self.records["full"]]
        rows = [self.rows["full_custom"]]
        self.assertEqual(formatter.to_csv(recs), rows)

        # Then do a test with only having custom fields
        formatter = Formatter(
            EC2_POLICY.resource_manager.resource_type,
            extra_fields=extra_fields,
            include_default_fields=False,
        )
        recs = [self.records["full"]]
        rows = [self.rows["minimal_custom"]]
        self.assertEqual(formatter.to_csv(recs), rows)


class TestASGReport(unittest.TestCase):

    def setUp(self):
        data = load_data("report.json")
        self.records = data["asg"]["records"]
        self.headers = data["asg"]["headers"]
        self.rows = data["asg"]["rows"]

    def test_csv(self):
        formatter = Formatter(ASG_POLICY.resource_manager.resource_type)
        tests = [
            (["full"], ["full"]),
            (["minimal"], ["minimal"]),
            (["full", "minimal"], ["full", "minimal"]),
            (["full", "duplicate", "minimal"], ["full", "minimal"]),
        ]
        for rec_ids, row_ids in tests:
            recs = list(map(lambda x: self.records[x], rec_ids))
            rows = list(map(lambda x: self.rows[x], row_ids))
            self.assertEqual(formatter.to_csv(recs), rows)


class TestELBReport(unittest.TestCase):

    def setUp(self):
        data = load_data("report.json")
        self.records = data["elb"]["records"]
        self.headers = data["elb"]["headers"]
        self.rows = data["elb"]["rows"]

    def test_csv(self):
        formatter = Formatter(ELB_POLICY.resource_manager.resource_type)
        tests = [
            (["full"], ["full"]),
            (["minimal"], ["minimal"]),
            (["full", "minimal"], ["full", "minimal"]),
            (["full", "duplicate", "minimal"], ["full", "minimal"]),
        ]
        for rec_ids, row_ids in tests:
            recs = list(map(lambda x: self.records[x], rec_ids))
            rows = list(map(lambda x: self.rows[x], row_ids))
            self.assertEqual(formatter.to_csv(recs), rows)


class TestMultiReport(unittest.TestCase):

    def setUp(self):
        data = load_data("report.json")
        self.records = data["ec2"]["records"]
        self.headers = data["ec2"]["headers"]
        self.rows = data["ec2"]["rows"]

    def test_csv(self):
        # Test the extra headers for multi-policy
        formatter = Formatter(
            EC2_POLICY.resource_manager.resource_type,
            include_region=True,
            include_policy=True,
        )
        tests = [(["minimal"], ["minimal_multipolicy"])]
        for rec_ids, row_ids in tests:
            recs = list(map(lambda x: self.records[x], rec_ids))
            rows = list(map(lambda x: self.rows[x], row_ids))
            self.assertEqual(formatter.to_csv(recs), rows)
