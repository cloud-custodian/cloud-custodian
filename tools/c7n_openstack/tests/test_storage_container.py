# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_openstack import OpenStackTest


class UserTest(OpenStackTest):

    def test_storage_container_public(self):
        factory = self.replay_flight_data('test_storage_container_public')
        policy = {
            'name': 'storage-container-public',
            'resource': 'openstack.storage-container',
            'filters': [
                {
                    "type": "value",
                    "key": "read_ACL",
                    "value": ".r:*,.rlistings"
                }
            ],
        }
        p = self.load_policy(policy, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['read_ACL'], '.r:*,.rlistings')
