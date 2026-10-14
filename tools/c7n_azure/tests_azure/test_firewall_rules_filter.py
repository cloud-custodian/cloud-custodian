# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

from .azure_common import BaseTest
from c7n_azure.filters import FirewallRulesFilter
from unittest.mock import Mock
from netaddr import IPRange, IPNetwork, IPSet


class FirewallRulesFilterTest(BaseTest):

    def test_firewall_rules_include_empty(self):
        satisfying_resources = [
            {'rules': [IPRange('2.0.0.0', '2.0.0.20')]},
            {'rules': [IPNetwork('0.0.0.1')]},
            # repeat
            {'rules': [IPRange('2.0.0.0', '2.0.0.20')]},
            {'rules': [IPNetwork('0.0.0.1')]},
        ]

        mock = FirewallRulesFilterMock({'include': []}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources)
        self.assertEqual(satisfying_resources, actual)

    def test_firewall_rules_include(self):
        required_rules = [
            IPNetwork('1.0.0.20/10'),
            IPNetwork('0.0.0.0'),
            IPRange('2.0.0.0', '2.0.0.10')]

        satisfying_resources = [
            {'rules': required_rules},
            {'rules': required_rules + [IPRange('2.0.0.0', '2.0.0.20')]},
            {'rules': required_rules + [IPNetwork('0.0.0.1')]},
            # repeat
            {'rules': required_rules},
            {'rules': required_rules + [IPRange('2.0.0.0', '2.0.0.20')]},
            {'rules': required_rules + [IPNetwork('0.0.0.1')]},
        ]

        non_satisfying_resources = [
            {'rules': []},
            {'rules': [IPNetwork('0.0.0.1')]},
            {'rules': [required_rules[0], required_rules[1]]},
        ]

        mock = FirewallRulesFilterMock({'include': [
            '0.0.0.0-0.0.0.0',
            '1.0.0.20/10',
            '2.0.0.0-2.0.0.10'
        ]}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources + non_satisfying_resources)
        self.assertEqual(satisfying_resources, actual)

    def test_firewall_rules_only(self):
        required_rules = [
            IPNetwork('1.0.0.20/10'),
            IPNetwork('0.0.0.0'),
            IPRange('2.0.0.0', '2.0.0.10')]

        satisfying_resources = [
            {'rules': required_rules},
            {'rules': [required_rules[0], required_rules[1]]}
        ]

        non_satisfying_resources = [
            {'rules': [IPNetwork('0.0.0.1')]},
            {'rules': required_rules + [IPRange('2.0.0.0', '2.0.0.20')]}
        ]

        mock = FirewallRulesFilterMock({'only': [
            '0.0.0.0-0.0.0.0',
            '1.0.0.20/10',
            '2.0.0.0-2.0.0.10',
            '8.8.8.8'
        ]}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources + non_satisfying_resources)
        self.assertEqual(satisfying_resources, actual)

    def test_firewall_rules_any(self):
        required_rules = [
            IPNetwork('1.0.0.20/10'),
            IPNetwork('0.0.0.0'),
            IPRange('2.0.0.0', '2.0.0.10')]

        satisfying_resources = [
            {'rules': required_rules},
            {'rules': [required_rules[0], required_rules[1]]},
            {'rules': required_rules + [IPRange('2.0.0.0', '2.0.0.20')]}
        ]

        non_satisfying_resources = [
            {'rules': [IPNetwork('0.0.0.1')]}
        ]

        mock = FirewallRulesFilterMock({'any': [
            '0.0.0.0-0.0.0.0',
            '1.0.0.20/10',
            '2.0.0.0-2.0.0.10',
            '8.8.8.8'
        ]}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources + non_satisfying_resources)
        self.assertEqual(satisfying_resources, actual)

    def test_firewall_rules_equal_empty(self):
        satisfying_resources = [
            {'rules': []},
        ]

        non_satisfying_resources = [
            {'rules': [IPNetwork('0.0.0.1')]},
            {'rules': [IPRange('2.0.0.0', '2.0.0.20')]},
            {'rules': [IPNetwork('0.0.0.1')]},
        ]

        mock = FirewallRulesFilterMock({'equal': []}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources + non_satisfying_resources)
        self.assertEqual(satisfying_resources, actual)

    def test_firewall_rules_equal(self):
        required_rules = [
            IPNetwork('1.0.0.20/10'),
            IPNetwork('0.0.0.0'),
            IPRange('2.0.0.0', '2.0.0.10')]

        satisfying_resources = [
            {'rules': required_rules},
            {'rules': required_rules},
        ]

        non_satisfying_resources = [
            {'rules': []},
            {'rules': [IPNetwork('0.0.0.1')]},
            {'rules': [required_rules[0], required_rules[1]]},
            {'rules': required_rules + [IPRange('2.0.0.0', '2.0.0.20')]},
            {'rules': required_rules + [IPNetwork('0.0.0.1')]},
        ]

        mock = FirewallRulesFilterMock({'equal': [
            '0.0.0.0-0.0.0.0',
            '1.0.0.20/10',
            '2.0.0.0-2.0.0.10'
        ]}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources + non_satisfying_resources)
        self.assertEqual(satisfying_resources, actual)


class FirewallRulesFilterMock(FirewallRulesFilter):

    @property
    def log(self):
        return logging.Logger.root

    def _query_rules(self, resource):
        rules = IPSet()
        for r in resource['rules']:
            rules.add(r)

        return rules
