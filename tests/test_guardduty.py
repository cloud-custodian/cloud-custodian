from __future__ import absolute_import, division, print_function, unicode_literals

from .common import BaseTest


class TestGuardDuty(BaseTest):

    def test_list_invitations(self):
        factory = self.replay_flight_data("test_guardduty")
        p = self.load_policy(
            {
                "name": "test-guarduty-invitation",
                "resource": "guardduty-invitations",
                "filters": [
                    {"type": "list-invitations", "key": "AccountId", "value": "601425634627"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_list_invitations_nomatch(self):
        factory = self.replay_flight_data("test_guardduty")
        p = self.load_policy(
            {
                "name": "test-guarduty-invitation",
                "resource": "guardduty-invitations",
                "filters": [
                    {"type": "list-invitations", "key": "AccountId", "value": "601425634628"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_accept_invitation(self):
        factory = self.replay_flight_data("test_guardduty")
        p = self.load_policy(
            {
                "name": "test-guarduty-invitation",
                "resource": "guardduty-invitations",
                "filters": [
                    {"type": "list-invitations", "key": "AccountId", "value": "601425634627"}
                ],
                "actions": ["accept-invitation"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_list_detectors(self):
        factory = self.replay_flight_data("test_guardduty")
        p = self.load_policy(
            {
                "name": "test-guarduty-detectors",
                "resource": "guardduty-detectors",
                "filters": [
                    {"type": "list-detectors"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
