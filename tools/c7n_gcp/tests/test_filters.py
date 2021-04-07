# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from gcp_common import BaseTest


class TestGCPMetricsFilter(BaseTest):

    def test_metrics(self):

        session_factory = self.replay_flight_data("filter-metrics")

        p = self.load_policy(
            {
                "name": "test-metrics",
                "resource": "gcp.instance",
                "filters": [
                    {'type': 'metrics',
                    'name': 'compute.googleapis.com/instance/cpu/utilization',
                    'metric-key': 'metric.labels.instance_name',
                    'resource-key': 'name',
                    'aligner': 'ALIGN_MEAN',
                    'days': 14,
                    'value': .1,
                    'filter': ' resource.labels.zone = "us-east4-c"',
                    'op': 'less-than'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        metric_name = 'compute.googleapis.com/instance/cpu/utilization.ALIGN_MEAN.REDUCE_NONE'
        metric = resources[0]['c7n.metrics'][metric_name]
        self.assertGreater(.1, metric['points'][0]['value']['doubleValue'])

    def test_no_metrics_found(self):

        session_factory = self.replay_flight_data("filter-no-metrics")

        p = self.load_policy(
            {
                "name": "test-metrics",
                "resource": "gcp.instance",
                "filters": [
                    {'type': 'metrics',
                    'name': 'compute.googleapis.com/instance/cpu/utilization',
                    'metric-key': 'metric.labels.instance_name',
                    'resource-key': 'name',
                    'aligner': 'ALIGN_MEAN',
                    'days': 14,
                    'value': .1,
                    'filter': ' resource.labels.zone = "us-east4-d"',
                    'op': 'less-than'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)


class TestSecurityComandCenterFindingsFilter(BaseTest):

    def test_findings(self):

        session_factory = self.replay_flight_data("filter-scc-findings")

        p = self.load_policy(
            {
                "name": "test-scc-findings",
                "resource": "gcp.bucket",
                "filters": [
                    {'type': 'scc-findings',
                     'org': '111111111111',
                     'key': '[].finding.category',
                     'value': 'BUCKET_LOGGING_DISABLED',
                     'op': 'contains'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n.findings'][0]['finding']['category'],
          'BUCKET_LOGGING_DISABLED')

    def test_findings_no_key(self):

        session_factory = self.replay_flight_data("filter-scc-findings")

        p = self.load_policy(
            {
                "name": "test-scc-findings",
                "resource": "gcp.bucket",
                "filters": [
                    {'type': 'scc-findings',
                     'org': '111111111111'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
