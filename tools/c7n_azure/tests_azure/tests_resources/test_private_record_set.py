# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from ..azure_common import BaseTest, arm_template, cassette_name
from c7n_azure.query import ChildTypeInfo
from c7n_azure.resources.private_record_set import PrivateRecordSet
from c7n_azure.utils import ResourceIdParser


class PrivateRecordSetTest(BaseTest):

    def test_private_record_set_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'azure-private-record-set-policy',
                'resource': 'azure.private-record-set'
            }, validate=True)
            self.assertTrue(p)

        # Record sets carry metadata rather than tags, so the ARM tagging
        # actions must not be registered.
        for action in ('tag', 'untag', 'auto-tag-user', 'auto-tag-date',
                       'tag-trim', 'mark-for-op'):
            self.assertNotIn(action, PrivateRecordSet.action_registry)
        self.assertNotIn('marked-for-op', PrivateRecordSet.filter_registry)

    @arm_template('private-dns.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-find-by-name',
            'resource': 'azure.private-record-set',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'www'
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'www')
        self.assertEqual(resources[0]['type'], 'Microsoft.Network/privateDnsZones/A')
        self.assertTrue(
            ResourceIdParser.get_resource_name(
                resources[0][ChildTypeInfo.parent_key]).startswith('c7n-test.'))

    @arm_template('private-dns.json')
    @cassette_name('test_find_by_name')
    def test_enumerates_every_zone(self):
        p = self.load_policy({
            'name': 'test-enumerates-every-zone',
            'resource': 'azure.private-record-set'
        })

        resources = p.run()
        zones = {ResourceIdParser.get_resource_name(r[ChildTypeInfo.parent_key])
                 for r in resources}
        self.assertEqual(len(zones), 2)
