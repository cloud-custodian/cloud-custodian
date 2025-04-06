# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
from ..azure_common import BaseTest, arm_template
from c7n.testing import mock_datetime_now
from dateutil.parser import parse as date_parse


class DiskTest(BaseTest):
    def setUp(self):
        super(DiskTest, self).setUp()

    def test_azure_disk_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-disk',
                'resource': 'azure.disk'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('disk.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-disk',
            'resource': 'azure.disk',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value': 'cctestvm_OsDisk_1_81338ced63fa4855b8a5f3e2bab5213c'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('disk.json')
    def test_disk_without_snapshots(self):
        p = self.load_policy({
            'name': 'test-disk-with-snapshots-within-14-days',
            'resource': 'azure.disk',
            'filters': [{
                'type': 'snapshots',
                'attrs': [{
                    'type': 'value',
                    'key': 'properties.timeCreated',
                    'op': 'le',
                    'value': 14,
                    'value_type': 'age'
                }]
            }]
        })
        with mock_datetime_now(date_parse('2021/04/01 00:00'), datetime):
            resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual('cctestvm_disk2_a9097edcfa664ff48c8e88e87d72003e',
                         resources[0]['name'])
