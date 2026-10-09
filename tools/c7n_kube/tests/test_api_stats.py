# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import os
from unittest.mock import MagicMock, patch

from common_kube import KubeTest

from c7n.output import LogMetrics
from c7n_kube import client as kube_client
from c7n_kube.client import APIStats, InstrumentedAPI


class TestAPIStats(KubeTest):
    def test_policy_run_records_api_calls(self):
        # The pagination flight replays 3 pages, so a policy run makes three
        # list calls through the client.
        factory = self.replay_flight_data("TestQueryPagination.test_pagination_multi_page.yaml")
        output_dir = self.get_temp_dir()
        p = self.load_policy(
            {"name": "config-maps", "resource": "k8s.config-map"},
            session_factory=factory,
            output_dir=output_dir,
        )
        metrics = []
        with patch.object(LogMetrics, "_put_metrics", lambda self, ns, m: metrics.extend(m)):
            resources = p.run()
        self.assertEqual(len(resources), 6)

        with open(os.path.join(output_dir, "config-maps", "metadata.json")) as fh:
            metadata = json.load(fh)
        self.assertEqual(metadata["api-stats"], {"list_config_map_for_all_namespaces": 3})

        by_name = {m["MetricName"]: m for m in metrics}
        self.assertEqual(by_name["ApiCalls"]["Value"], 3)
        self.assertEqual(by_name["ApiCalls"]["Unit"], "Count")
        self.assertEqual(by_name["ApiTime"]["Unit"], "Seconds")
        self.assertGreater(by_name["ApiTime"]["Value"], 0)
        self.assertEqual(kube_client._subscribers, [])

    def test_records_failed_calls(self):
        api = MagicMock()
        api.patch_namespaced_deployment.side_effect = ValueError("boom")
        stats = APIStats(MagicMock())
        stats.__enter__()
        try:
            with self.assertRaises(ValueError):
                InstrumentedAPI(api).patch_namespaced_deployment(name="x")
        finally:
            stats.__exit__()
        self.assertEqual(stats.get_metadata(), {"patch_namespaced_deployment": 1})

    def test_no_recording_outside_execution(self):
        api = MagicMock()
        api.list_namespace.return_value = "result"
        stats = APIStats(MagicMock())
        self.assertEqual(InstrumentedAPI(api).list_namespace(), "result")
        self.assertEqual(stats.get_metadata(), {})

    def test_non_callable_attributes_pass_through(self):
        api = MagicMock()
        api.api_client = "the-api-client"
        self.assertEqual(InstrumentedAPI(api).api_client, "the-api-client")
