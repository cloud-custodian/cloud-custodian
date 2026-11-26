# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest import mock

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

    def test_gamelift_fleet_tag_actions_use_fleet_arn(self):
        arn = 'arn:aws:gamelift:us-east-1:644160558196:fleet/fleet-1'
        factory = mock.MagicMock()
        factory.region = 'us-east-1'
        tagging = factory().client('resourcegroupstaggingapi')
        tagging.tag_resources.return_value = {}
        tagging.untag_resources.return_value = {}
        policy = self.load_policy(
            {'name': 'gamelift-fleet-tag-actions', 'resource': 'gamelift-fleet',
             'actions': [{'type': 'tag', 'tags': {'owner': 'c7n'}},
                         {'type': 'remove-tag', 'tags': ['owner']}]},
            session_factory=factory)
        for action in policy.resource_manager.actions:
            action.process([{'FleetId': 'fleet-1', 'FleetArn': arn}])
        tagging.tag_resources.assert_called_once_with(
            ResourceARNList=[arn], Tags={'owner': 'c7n'})
        tagging.untag_resources.assert_called_once_with(
            ResourceARNList=[arn], TagKeys=['owner'])
