# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_openstack import OpenStackTest


class UserTest(OpenStackTest):

    def test_user_extended_info_filter(self):
        factory = self.replay_flight_data('test_user_extended_info_filter')
        policy = {
            'name': 'user-with-disabled-mfa',
            'resource': 'openstack.user',
            'filters': [
                {
                    "or": [
                        {
                            "type": "extended-info",
                            "key": "options.multi_factor_auth_enabled",
                            "value": "absent"
                        },
                        {
                            "type": "extended-info",
                            "key": "options.multi_factor_auth_enabled",
                            "value": False
                        }
                    ]
                },
            ],
        }
        p = self.load_policy(policy, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(len(resources[0]["c7n:ExtendedUserInfo"]["options"]), 0)
