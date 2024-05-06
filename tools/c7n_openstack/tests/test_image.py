# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_openstack import OpenStackTest


class UserTest(OpenStackTest):

    def test_image_signed(self):
        factory = self.replay_flight_data('test_image_signed')
        policy = {
            'name': 'image-signed',
            'resource': 'openstack.image',
            'filters': [
                {
                    "type": "value",
                    "key": "img_signature",
                    "value": "present"
                }
            ],
        }
        p = self.load_policy(policy, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn("img_signature", resources[0])
