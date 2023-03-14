# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from ..azure_common import BaseTest, arm_template
from c7n.utils import local_session
from c7n_azure.query import ChildTypeInfo
from c7n_azure.session import Session
from c7n_azure.utils import ResourceIdParser


class RecordSetTest(BaseTest):

    def test_record_set_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'record-set-policy',
                'resource': 'azure.recordset'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('dns.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-find-by-name',
            'resource': 'azure.recordset',
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


class DeleteRecordSetTest(BaseTest):

    @classmethod
    def setUpClass(cls, *args, **kwargs):
        super(DeleteRecordSetTest, cls).setUpClass(*args, **kwargs)
        cls.client = local_session(Session).client('azure.mgmt.dns.DnsManagementClient').record_sets

    def tearDown(self, *args, **kwargs):
        super(DeleteRecordSetTest, self).tearDown(*args, **kwargs)

        rs = self.deleted_recordset
        rs_id = rs['id']
        rs_parent_id = rs[ChildTypeInfo.parent_key]
        zone_name = ResourceIdParser.get_resource_name(rs_parent_id)
        rs_name = ResourceIdParser.get_resource_name(rs_id)
        rs_type = rs['type'].split('/')[-1]
        rs_ttl = rs['properties']['TTL']
        rs_arecord_ipaddr = rs['properties']['ARecords'][0]['ipv4Address']

        DeleteRecordSetTest.client.create_or_update(
            resource_group_name=rs['resourceGroup'],
            zone_name=zone_name,
            relative_record_set_name=rs_name,
            record_type=rs_type,
            parameters={
                'ttl': rs_ttl,
                'arecords': [
                    {
                        'ipv4_address': rs_arecord_ipaddr
                    }
                ]
            },
        )

    @arm_template('dns.json')
    def test_delete_a_record_set(self):

        record_set_name = 'deleteme'

        p = self.load_policy({
            'name': 'test-delete-a-record-set',
            'resource': 'azure.recordset',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': record_set_name
                }
            ],
            'actions': [
                {
                    'type': 'delete'
                }
            ]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], record_set_name)

        rs = resources[0]
        self.deleted_recordset = rs
        rg = rs['resourceGroup']
        zone = ResourceIdParser.get_resource_name(rs[ChildTypeInfo.parent_key])

        self._assert_record_set_not_present(record_set_name, rg, zone)

    def _assert_record_set_not_present(self, name, resource_group, dns_zone):
        record_sets = DeleteRecordSetTest.client.list_by_dns_zone(resource_group, dns_zone)
        record_set = next((rs for rs in record_sets if rs.name == name), None)
        self.assertIsNone(record_set)
