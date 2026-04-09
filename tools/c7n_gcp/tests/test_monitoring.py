# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from gcp_common import BaseTest


class MonitoringNotificationChannelTest(BaseTest):
    def test_query(self):
        factory = self.replay_flight_data('monitoring-notification-channel-query')
        p = self.load_policy(
            {
                'name': 'monitoring-notification-channel',
                'resource': 'gcp.monitoring-notification-channel',
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['type'], 'email')
        self.assertTrue(resources[0]['enabled'])
