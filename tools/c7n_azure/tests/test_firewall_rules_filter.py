# Copyright 2015-2018 Capital One Services, LLC
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

import logging

from azure_common import BaseTest
from c7n_azure.filters import FirewallRulesFilter
from jsonschema import ValidationError
from netaddr import IPRange, IPNetwork, IPSet

from c7n.exceptions import PolicyValidationError


class FirewallRulesFilterTest(BaseTest):

    def test_firewall_rules_include_empty(self):
        satisfying_resources = [
            {'rules': [IPRange('2.0.0.0', '2.0.0.20')]},
            {'rules': [IPNetwork('0.0.0.1')]},
            # repeat
            {'rules': [IPRange('2.0.0.0', '2.0.0.20')]},
            {'rules': [IPNetwork('0.0.0.1')]},
        ]

        mock = FirewallRulesFilterMock({'include': []})

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
        ]})

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
        ]})

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
        ]})

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

        mock = FirewallRulesFilterMock({'equal': []})

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
        ]})

        mock.validate()
        actual = mock.process(satisfying_resources + non_satisfying_resources)
        self.assertEqual(satisfying_resources, actual)

    def test_firewall_bad_schema(self):
        p = self.load_policy({
            'name': 'test-azure-storage',
            'resource': 'azure.storage',
            'filters': [{
                'type': 'firewall-rules'
            }],
        })
        with self.assertRaises(ValidationError):
            self.load_policy(data=p, validate=True)

    def test_firewall_invalid_range(self):
        with self.assertRaises(PolicyValidationError):
            mock = FirewallRulesFilterMock({'include': ['0.0.0.1-0.0.0.0']})
            mock.validate()


class FirewallRulesFilterMock(FirewallRulesFilter):

    @property
    def log(self):
        return logging.Logger.root

    def _query_rules(self, resource):
        rules = IPSet()
        for r in resource['rules']:
            rules.add(r)

        return rules
