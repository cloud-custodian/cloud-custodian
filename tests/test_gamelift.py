# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestGameLiftFleet(BaseTest):

    def test_gamelift_fleet_tag(self):
        session_factory = self.replay_flight_data('test_gamelift_fleet_tag')
        p = self.load_policy(
            {
                'name': 'gamelift-fleet-tag',
                'resource': 'gamelift-fleet',
                'filters': [{'tag:owner': 'absent'}],
                'actions': [{'type': 'tag', 'tags': {'owner': 'c7n'}}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'test-fleet')
