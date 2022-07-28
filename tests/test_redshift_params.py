# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestRedshiftParameterGroup(BaseTest):

    def test_redshift_cluster_parameter_group_filter(self):
        factory = self.replay_flight_data("test_redshift_cluster_parameter_group")
        p = self.load_policy(
            {
                "name": "redshift-test-param",
                "resource": "redshift-param-group",
                "filters": [
                    {
                        "type": "check-require-ssl-status"
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        print(resources)
        if resources:
            print("Filter worked successfully!!")
        else:
            self.fail("Test failed!!")
        self.assertEqual(len(resources), 1)

    def test_redshift_cluster_parameter_group_action(self):
        factory = self.replay_flight_data("test_redshift_cluster_parameter_group_action")
        p = self.load_policy(
            {
                "name": "redshift-test-param-action",
                "resource": "redshift-param-group",
                "filters": [
                    {
                        "type": "check-require-ssl-status"
                    }
                ],
                "actions": [
                    {
                        "type": "update-parameter-group"
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        if resources:
            print("Action worked successfully!!")
        else:
            self.fail("Test failed!!")
        self.assertEqual(len(resources), 1)
