# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.reports.csvout import Formatter
from .common import BaseTest, load_data


class TestEC2Report(BaseTest):

    def setUp(self):
        data = load_data("report.json")
        self.records = data["ec2"]["records"]
        self.headers = data["ec2"]["headers"]
        self.rows = data["ec2"]["rows"]
        self.p = self.load_policy({"name": "report-test-ec2", "resource": "ec2"})

    def test_default_csv(self):
        self.patch(self.p.resource_manager.resource_type,
                   'default_report_fields', ())
        formatter = Formatter(self.p.resource_manager.resource_type)
        self.assertEqual(
            formatter.to_csv([self.records['full']]),
            [['InstanceId-1', '', 'LaunchTime-1']])

    def test_csv(self):
        p = self.load_policy({"name": "report-test-ec2", "resource": "ec2"})
        formatter = Formatter(p.resource_manager.resource_type)
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
            self.p.resource_manager.resource_type, extra_fields=extra_fields
        )
        recs = [self.records["full"]]
        rows = [self.rows["full_custom"]]
        self.assertEqual(formatter.to_csv(recs), rows)

        # Then do a test with only having custom fields
        formatter = Formatter(
            self.p.resource_manager.resource_type,
            extra_fields=extra_fields,
            include_default_fields=False,
        )
        recs = [self.records["full"]]
        rows = [self.rows["minimal_custom"]]
        self.assertEqual(formatter.to_csv(recs), rows)


class TestASGReport(BaseTest):

    def setUp(self):
        data = load_data("report.json")
        self.records = data["asg"]["records"]
        self.headers = data["asg"]["headers"]
        self.rows = data["asg"]["rows"]

    def test_csv(self):
        p = self.load_policy({"name": "report-test-asg", "resource": "asg"})
        formatter = Formatter(p.resource_manager.resource_type)
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


class TestELBReport(BaseTest):

    def setUp(self):
        data = load_data("report.json")
        self.records = data["elb"]["records"]
        self.headers = data["elb"]["headers"]
        self.rows = data["elb"]["rows"]

    def test_csv(self):
        p = self.load_policy({"name": "report-test-elb", "resource": "elb"})
        formatter = Formatter(p.resource_manager.resource_type)
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


class TestMultiReport(BaseTest):

    def setUp(self):
        data = load_data("report.json")
        self.records = data["ec2"]["records"]
        self.headers = data["ec2"]["headers"]
        self.rows = data["ec2"]["rows"]

    def test_csv(self):
        # Test the extra headers for multi-policy
        p = self.load_policy({"name": "report-test-ec2", "resource": "ec2"})
        formatter = Formatter(
            p.resource_manager.resource_type,
            include_region=True,
            include_policy=True,
        )
        tests = [(["minimal"], ["minimal_multipolicy"])]
        for rec_ids, row_ids in tests:
            recs = list(map(lambda x: self.records[x], rec_ids))
            rows = list(map(lambda x: self.rows[x], row_ids))
            self.assertEqual(formatter.to_csv(recs), rows)
