# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_openstack import OpenStackTest


class VolumeTest(OpenStackTest):

    def test_secret_without_expiration(self):
        factory = self.replay_flight_data('test_secret_without_expiration')
        p = self.load_policy({
            'name': 'secrets-without-expiration',
            'resource': 'openstack.secret',
            'filters': [
                {
                    'type': 'value',
                    'key': 'expires_at',
                    'value': None
                }
            ]
        },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertIsNone(resources[0]['expires_at'])
        self.assertIsNone(resources[1]['expires_at'])
