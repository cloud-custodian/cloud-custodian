# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class SessionHostsTest(BaseTest):
    def test_session_hosts_schema_validate(self):
        p = self.load_policy({
            'name': 'test-session-hosts',
            'resource': 'azure.session-hosts'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-session-hosts-by-name',
            'resource': 'azure.session-hosts',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': '*/cfb-test*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_session_hosts_all(self):
        p = self.load_policy({
            'name': 'test-session-hosts',
            'resource': 'azure.session-hosts',
            'filters': [
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_session_hosts_vm(self):
        p = self.load_policy({
            'name': 'test-sh-vm-iv',
            'resource': 'azure.session-hosts',
            'filters': [
                 {'type': 'session-hosts-vm',
                 'key': 'properties.instanceView.statuses[].code',
                  'op': 'in',
                  'value_type': 'swap',
                  'value': 'PowerState/running'
                },
                {'type': 'session-hosts-vm',
                  'key': 'identity',
                  'value': 'absent'
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 2)

