# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class IoTHubTest(BaseTest):
    def setUp(self):
        super(IoTHubTest, self).setUp()

    def test_iot_hub_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-iot-hub-compliance',
                'resource': 'azure.iothub'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('iothub.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-iothub',
            'resource': 'azure.iothub',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': 'cctest-iothub*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
