# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import jmespath
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
                        "type": "enable-require-ssl-parameter-group"
                    }
                ]
            },
            session_factory=factory
        )
        resources = p.run()
        client = factory().client('redshift')
        response = client.describe_cluster_parameters(
            ParameterGroupName=resources[0])
        param_val = jmespath.search(
            "Parameters[?ParameterName=='require_ssl'].ParameterValue", response)
        self.assertEqual(param_val[0], 'true')

