# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import os
from unittest.mock import MagicMock, patch

from gcp_common import BaseTest

from c7n import output
from c7n.output import LogMetrics
from c7n_gcp.client import ApiStats, ServiceClient


class ApiStatsTest(BaseTest):

    def test_policy_run_records_api_calls(self):
        # The flight replays two pages of roles, so a policy run makes two
        # list calls.
        factory = self.replay_flight_data("ami-role-query", self.project_id)
        output_dir = self.get_temp_dir()
        p = self.load_policy(
            {"name": "iam-roles", "resource": "gcp.iam-role"},
            session_factory=factory,
            output_dir=output_dir,
        )
        metrics = []
        with patch.object(LogMetrics, "_put_metrics", lambda self, ns, m: metrics.extend(m)):
            resources = p.run()
        self.assertEqual(len(resources), 2)

        with open(os.path.join(output_dir, "iam-roles", "metadata.json")) as fh:
            metadata = json.load(fh)
        self.assertEqual(metadata["api-stats"], {"iam.roles.list": 2})

        by_name = {m["MetricName"]: m for m in metrics}
        self.assertEqual(by_name["ApiCalls"]["Value"], 2)
        self.assertEqual(by_name["ApiCalls"]["Unit"], "Count")
        self.assertEqual(by_name["ApiTime"]["Unit"], "Seconds")
        self.assertGreater(p.ctx.api_stats.api_time, 0)
        self.assertEqual(by_name["ApiTime"]["Value"], round(p.ctx.api_stats.api_time, 3))
        self.assertEqual(output._api_call_recorders, [])

    def test_records_failed_calls(self):
        client = ServiceClient.__new__(ServiceClient)
        request = MagicMock(methodId="compute.instances.delete")
        stats = ApiStats(MagicMock())
        stats.__enter__()
        try:
            with patch.object(
                ServiceClient, "_execute_with_retry", side_effect=ValueError("boom")
            ):
                with self.assertRaises(ValueError):
                    client._execute(request)
        finally:
            stats.__exit__()
        self.assertEqual(stats.get_metadata(), {"compute.instances.delete": 1})
