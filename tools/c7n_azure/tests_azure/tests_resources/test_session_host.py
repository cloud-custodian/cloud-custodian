# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest


class SessionHostTest(BaseTest):
    def test_session_host_schema_validate(self):
        p = self.load_policy({
            'name': 'test-session-host-schema',
            'resource': 'azure.session-host'
        }, validate=True)
        self.assertTrue(p)

    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-session-host-by-name',
            'resource': 'azure.session-host',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': '*/cfb-test*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_session_host_all(self):
        p = self.load_policy({
            'name': 'test-session-host',
            'resource': 'azure.session-host',
            'filters': [
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_session_host_vm(self):
        p = self.load_policy({
            'name': 'test-sh-vm-iv',
            'resource': 'azure.session-host',
            'filters': [
                 {'type': 'session-host-vm',
                 'key': 'properties.instanceView.statuses[].code',
                  'op': 'in',
                  'value_type': 'swap',
                  'value': 'PowerState/running'
                },
                {'type': 'session-host-vm',
                  'key': 'identity',
                  'value': 'absent'
                }
            ]
        })
        resources = p.run()
        self.assertEqual(len(resources), 2)
