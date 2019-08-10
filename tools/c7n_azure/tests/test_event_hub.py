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

from azure_common import BaseTest, arm_template, cassette_name


class EventHubTest(BaseTest):

    def test_event_hub_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-event-hub-compliance',
                'resource': 'azure.eventhub'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('eventhub.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-eventhub',
            'resource': 'azure.eventhub',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'contains',
                 'value_type': 'normalize',
                 'value': '-cctesteventhubns'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @cassette_name('firewall')
    def test_firewall_rules_include_cidr(self):
        p = self.load_policy({
            'name': 'test-azure-eventhub',
            'resource': 'azure.eventhub',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'contains',
                 'value_type': 'normalize',
                 'value': '-cctesteventhubns'},
                {'type': 'firewall-rules',
                 'include': ['11.0.0.0/24']}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @cassette_name('firewall')
    def test_firewall_rules_not_include_cidr(self):
        p = self.load_policy({
            'name': 'test-azure-eventhub',
            'resource': 'azure.eventhub',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'contains',
                 'value_type': 'normalize',
                 'value': '-cctesteventhubns'},
                {'type': 'firewall-rules',
                 'include': ['11.0.1.0/24']}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @cassette_name('firewall')
    def test_firewall_rules_ranges(self):
        p = self.load_policy({
            'name': 'test-azure-eventhub',
            'resource': 'azure.eventhub',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'contains',
                 'value_type': 'normalize',
                 'value': '-cctesteventhubns'},
                {'type': 'firewall-rules',
                 'include': ['11.0.0.0-11.0.0.255']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @cassette_name('firewall')
    def test_firewall_rules_not_ranges(self):
        p = self.load_policy({
            'name': 'test-azure-eventhub',
            'resource': 'azure.eventhub',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'contains',
                 'value_type': 'normalize',
                 'value': '-cctesteventhubns'},
                {'type': 'firewall-rules',
                 'include': ['11.0.1.0-11.0.1.255']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))

    @cassette_name('firewall')
    def test_firewall_rules_equal(self):
        p = self.load_policy({
            'name': 'test-azure-eventhub',
            'resource': 'azure.eventhub',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'contains',
                 'value_type': 'normalize',
                 'value': '-cctesteventhubns'},
                {'type': 'firewall-rules',
                 'equal': ['11.0.0.0/24', '10.1.1.1/32']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(1, len(resources))

    @cassette_name('firewall')
    def test_firewall_rules_not_equal(self):
        p = self.load_policy({
            'name': 'test-azure-eventhub',
            'resource': 'azure.eventhub',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'contains',
                 'value_type': 'normalize',
                 'value': '-cctesteventhubns'},
                {'type': 'firewall-rules',
                 'equal': ['11.0.1.0/24', '10.1.1.1/32']}],
        }, validate=True)
        resources = p.run()
        self.assertEqual(0, len(resources))
