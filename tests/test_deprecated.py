# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest

from mock import Mock
from textwrap import dedent

from c7n import deprecated


class DeprecationTest(BaseTest):

    def test_action(self):
        deprecation = deprecated.action(
            "use modify-db instead with `CopyTagsToSnapshot`", '2021-06-30')
        # Always matches.
        self.assertTrue(deprecation.check({}))
        self.assertEqual(
            str(deprecation),
            "action has been deprecated (use modify-db instead with `CopyTagsToSnapshot`)"
        )

    def test_filter(self):
        deprecation = deprecated.filter(
            "use the 'used' filter with 'state' attribute", '2021-06-30')
        # Always matches.
        self.assertTrue(deprecation.check({}))
        self.assertEqual(
            str(deprecation),
            "filter has been deprecated (use the 'used' filter with 'state' attribute)"
        )

    def test_field(self):
        deprecation = deprecated.field('severity_normalized', 'severity_label', '2021-06-30')
        self.assertTrue(deprecation.check({'severity_normalized': '10'}))
        self.assertFalse(deprecation.check({'no-match': 'ignored'}))
        self.assertEqual(
            str(deprecation),
            "field 'severity_normalized' has been deprecated (replaced by 'severity_label')"
        )


class ReportTest(BaseTest):

    def test_empty(self):
        report = deprecated.Report("some-policy")
        self.assertFalse(report)
        self.assertEqual(report.format(), "policy 'some-policy'")

    def test_policy_source_locator(self):
        locator = Mock()
        locator.find.return_value = "somefile.yml:1234"
        report = deprecated.Report("some-policy")
        self.assertEqual(report.format(locator), "policy 'some-policy' (somefile.yml:1234)")
        locator.find.assert_called_with("some-policy")

    def test_conditions(self):
        report = deprecated.Report("some-policy", conditions=[
            deprecated.field('start', 'value filter in condition block', '2021-06-30'),
            deprecated.field('end', 'value filter in condition block', '2021-06-30'),
        ])
        self.assertTrue(report)
        self.assertEqual(report.format(), dedent("""
            policy 'some-policy'
              condition:
                field 'start' has been deprecated (replaced by value filter in condition block)
                field 'end' has been deprecated (replaced by value filter in condition block)
            """)[1:-1])

    def test_modes(self):
        report = deprecated.Report("some-policy", mode=[
            deprecated.field('foo', 'bar', '2021-06-30'),
            deprecated.field('baz', 'yet', '2021-06-30'),
        ])
        self.assertTrue(report)
        self.assertEqual(report.format(), dedent("""
            policy 'some-policy'
              mode:
                field 'foo' has been deprecated (replaced by 'bar')
                field 'baz' has been deprecated (replaced by 'yet')
            """)[1:-1])

    # No examples of resource deprecation just yet. Looking for one.

    def test_actions(self):
        report = deprecated.Report("some-policy", actions=[
            deprecated.Context(
                'mark-for-op:', deprecated.optional_fields(('hours', 'days'), '2021-06-30')),
            deprecated.Context(
                'mark-for-op:', deprecated.optional_field('tag', '2021-06-30')),
        ])
        self.assertTrue(report)
        self.assertEqual(report.format(), dedent("""
            policy 'some-policy'
              actions:
                mark-for-op: optional fields deprecated (one of 'hours' or 'days' must be specified)
                mark-for-op: optional field 'tag' deprecated (must be specified)
            """)[1:-1])

    def test_footnotes(self):
        footnotes = deprecated.Footnotes()
        report = deprecated.Report("some-policy", mode=[
            deprecated.field('foo', 'bar'),
            deprecated.field('baz', 'yet', '2021-06-30'),
        ], actions=[
            deprecated.Context(
                'mark-for-op:',
                deprecated.optional_fields(('hours', 'days'),
                                           link="http://docs.example.com/deprecations/foo#time")),
            deprecated.Context(
                'mark-for-op:',
                deprecated.optional_field('tag', '2021-06-30',
                                          "http://docs.example.com/deprecations/foo#tag")),
        ])
        self.assertTrue(report)
        self.assertEqual(report.format(footnotes=footnotes), dedent("""
            policy 'some-policy'
              mode:
                field 'foo' has been deprecated (replaced by 'bar')
                field 'baz' has been deprecated (replaced by 'yet') [1]
              actions:
                mark-for-op: optional fields deprecated (one of 'hours' or 'days' must be specified) [2]
                mark-for-op: optional field 'tag' deprecated (must be specified) [3]
            """)[1:-1])  # noqa
        self.assertEqual(footnotes(), dedent("""
            [1] Will be removed after 2021-06-30
            [2] See http://docs.example.com/deprecations/foo#time
            [3] See http://docs.example.com/deprecations/foo#tag, will become an error after 2021-06-30
            """)[1:-1])  # noqa
