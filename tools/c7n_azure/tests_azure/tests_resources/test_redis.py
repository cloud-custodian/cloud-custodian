# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template


class RedisTest(BaseTest):
    def setUp(self):
        super(RedisTest, self).setUp()

    def test_redis_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-redis',
                'resource': 'azure.redis'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('redis.json')
    def test_find_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-redis',
            'resource': 'azure.redis',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestredis*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)


class RedisFirewallFilterTest(BaseTest):

    def test_query(self):
        p = self.load_policy({
            'name': 'redis-firewall-filter',
            'resource': 'azure.redis',
            'filters': [
                {
                    'type': 'firewall',
                    'attrs': [{
                        'type': 'value',
                        'key': 'properties.startIP',
                        'value': '1.2.3.4'
                    }]
                }
            ]
        })
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], '301-redis-green')
