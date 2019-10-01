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

from .azure_common import BaseTest
from c7n_azure.filters import FirewallBypassFilter
from mock import Mock


class FirewallBypassFilterMock(FirewallBypassFilter):

    def _query_bypass(self, resource):
        return resource['bypass']


class FirewallBypassFilterTest(BaseTest):

    def test_include_empty(self):
        satisfying_resources = [
            {'bypass': ['AzureServices']},
            {'bypass': []},
        ]

        mock = FirewallBypassFilterMock({'mode': 'include', 'list': []}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources)
        self.assertEqual(satisfying_resources, actual)

    def test_include(self):
        required_rules = ['AzureServices', 'Test']

        satisfying_resources = [
            {'bypass': required_rules},
            {'bypass': required_rules + ['Extra']},
            {'bypass': required_rules + ['Extra2']},
        ]

        non_satisfying_resources = [
            {'bypass': []},
            {'bypass': ['Portal']},
            {'bypass': [required_rules[0], 'Extra']},
        ]

        mock = FirewallBypassFilterMock({'mode': 'include', 'list': required_rules}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources + non_satisfying_resources)
        self.assertEqual(satisfying_resources, actual)

    def test_only(self):
        required_rules = ['AzureServices', 'Test']

        satisfying_resources = [
            {'bypass': []},
            {'bypass': required_rules},
            {'bypass': required_rules[1:]},
            {'bypass': required_rules[:1]},
        ]

        non_satisfying_resources = [
            {'bypass': ['Portal']},
            {'bypass': required_rules + ['Extra']},
        ]

        mock = FirewallBypassFilterMock({'mode': 'only', 'list': required_rules}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources + non_satisfying_resources)
        self.assertEqual(satisfying_resources, actual)

    def test_any(self):
        required_rules = ['AzureServices', 'Test']

        satisfying_resources = [
            {'bypass': required_rules},
            {'bypass': required_rules[1:]},
            {'bypass': required_rules[:1]},
            {'bypass': required_rules[1:] + ['Test']},
            {'bypass': [required_rules[0], 'Test']},
        ]

        non_satisfying_resources = [
            {'bypass': []},
            {'bypass': ['Portal']},
        ]

        mock = FirewallBypassFilterMock({'mode': 'any', 'list': required_rules}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources + non_satisfying_resources)
        self.assertEqual(satisfying_resources, actual)

    def test_equal_empty(self):
        satisfying_resources = [
            {'bypass': []},
        ]

        non_satisfying_resources = [
            {'bypass': ['Portal']},
        ]

        mock = FirewallBypassFilterMock({'mode': 'equal', 'list': []}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources + non_satisfying_resources)
        self.assertEqual(satisfying_resources, actual)

    def test_equal(self):
        required_rules = ['AzureServices', 'Test']

        satisfying_resources = [
            {'bypass': required_rules},
        ]

        non_satisfying_resources = [
            {'bypass': []},
            {'bypass': ['Portal']},
            {'bypass': required_rules[1:]},
            {'bypass': required_rules[:1]},
            {'bypass': required_rules[1:] + ['Extra']},
            {'bypass': [required_rules[0], 'Extra']},
        ]

        mock = FirewallBypassFilterMock({'mode': 'equal', 'list': required_rules}, Mock())

        mock.validate()
        actual = mock.process(satisfying_resources + non_satisfying_resources)
        self.assertEqual(satisfying_resources, actual)
