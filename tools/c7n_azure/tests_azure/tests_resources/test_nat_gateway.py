# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class NatGatewayTest(BaseTest):

    def test_nat_gateway_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-azure-nat-gateway',
                'resource': 'azure.nat-gateway'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('nat-gateway.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-nat-gateway',
            'resource': 'azure.nat-gateway',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'value': 'cctestnatgw'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['sku']['name'], 'Standard')

    @arm_template('nat-gateway.json')
    def test_find_unattached(self):
        p = self.load_policy({
            'name': 'test-azure-nat-gateway-unattached',
            'resource': 'azure.nat-gateway',
            'filters': [
                {'type': 'value',
                 'key': 'properties.subnets',
                 'value': 'empty'},
                {'type': 'value',
                 'key': 'properties.publicIpAddresses',
                 'value': 'empty'},
                {'type': 'value',
                 'key': 'properties.publicIpPrefixes',
                 'value': 'empty'}],
        })
        resources = p.run()
        self.assertEqual([r['name'] for r in resources], ['cctestnatgwunused'])
