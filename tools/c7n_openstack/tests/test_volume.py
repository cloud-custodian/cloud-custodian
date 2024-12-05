# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from common_openstack import OpenStackTest


class VolumeTest(OpenStackTest):

    def test_volume_query(self):
        factory = self.replay_flight_data()
        p = self.load_policy({
            'name': 'all-volumes',
            'resource': 'openstack.volume'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
