# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class LoadBalancerTest(BaseTest):
    def setUp(self):
        super(LoadBalancerTest, self).setUp()

    def test_load_balancer_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-load-balancer',
                'resource': 'azure.loadbalancer',
                'filters': [
                    {'type': 'frontend-public-ip',
                     'key': 'properties.publicIPAddressVersion',
                     'op': 'in',
                     'value_type': 'normalize',
                     'value': 'ipv4'}
                ]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('load-balancer.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-loadbalancer',
            'resource': 'azure.loadbalancer',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestloadbalancer'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('load-balancer.json')
    def test_find_by_frontend_ip(self):
        p = self.load_policy({
            'name': 'test-loadbalancer-with-ipv6-frontend',
            'resource': 'azure.loadbalancer',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestloadbalancer'},
                {'type': 'frontend-public-ip',
                 'key': 'properties.publicIPAddressVersion',
                 'op': 'in',
                 'value_type': 'normalize',
                 'value': 'ipv4'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)
