# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest

class SESTest(BaseTest):

    def test_ses_configuration_set_query(self):
        session_factory = self.replay_flight_data("test_ses_configuration_set_query")
        p = self.load_policy(
            {
                "name": "ses-configuration-set-query-test",
                "resource": "ses-configuration-set"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)