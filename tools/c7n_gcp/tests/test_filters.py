# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from gcp_common import BaseTest
from c7n_gcp.filters.metrics import GCPMetricsFilter
from c7n.exceptions import PolicyExecutionError, PolicyValidationError


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

    def test_metrics_with_metric_key_as_instance_id(self):

        session_factory = self.replay_flight_data("filter-metrics-with-metric-key-as-instance-id")

        p = self.load_policy(
            {
                "name": "test-metrics",
                "resource": "gcp.instance",
                "filters": [
                    {'type': 'metrics',
                    'name': 'compute.googleapis.com/instance/cpu/utilization',
                    'metric-key': 'resource.labels.instance_id',
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

    def test_metrics_resource_regex(self):

        session_factory = self.replay_flight_data("filter-metrics")

        p = self.load_policy(
            {
                "name": "test-metrics",
                "resource": "gcp.instance",
                "filters": [
                    {'type': 'metrics',
                    'name': 'compute.googleapis.com/instance/cpu/utilization',
                    'metric-key': 'metric.labels.instance_name',
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

    def test_missing_value_zero_resource_has_no_metric(self):
        # metric-key doesn't match any label on the returned time series, so
        # this resource has no metric even though the batch's API response
        # wasn't empty. missing-value must still be applied per-resource.
        session_factory = self.replay_flight_data("filter-metrics")

        p = self.load_policy(
            {
                "name": "test-metrics",
                "resource": "gcp.instance",
                "filters": [
                    {'type': 'metrics',
                    'name': 'compute.googleapis.com/instance/cpu/utilization',
                    'metric-key': 'metric.labels.nonexistent',
                    'aligner': 'ALIGN_MEAN',
                    'days': 14,
                    'value': 1,
                    # 0 is falsy: the bug treated it the same as missing,
                    # dropping the resource instead of applying it.
                    'missing-value': 0,
                    'filter': ' resource.labels.zone = "us-east4-c"',
                    'op': 'less-than'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_missing_value_batch_has_no_metrics(self):
        # No time series data at all is returned for the batch, so
        # missing-value must still be applied per-resource instead of
        # short-circuiting the whole batch to no matches. missing-value is
        # non-zero here to isolate this from the missing-value: 0 fix above:
        # this test should fail solely because of the early return on an
        # empty batch, not because of the falsy-zero check.
        session_factory = self.replay_flight_data("filter-no-metrics")

        p = self.load_policy(
            {
                "name": "test-metrics",
                "resource": "gcp.instance",
                "filters": [
                    {'type': 'metrics',
                    'name': 'compute.googleapis.com/instance/cpu/utilization',
                    'metric-key': 'metric.labels.instance_name',
                    'aligner': 'ALIGN_MEAN',
                    'days': 14,
                    'value': -1,
                    'missing-value': -1,
                    # Recorded flight data has this instance in zone
                    # us-east4-c, so filtering on us-east4-d matches nothing:
                    # the API response has no timeSeries at all, and
                    # time_series_data defaults to [].
                    'filter': ' resource.labels.zone = "us-east4-d"',
                    'op': 'equal'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_metrics_missing_value_zero(self):
        # When a batch returns no metrics, a `missing-value` of 0 (a falsy but
        # valid default) must still be applied rather than dropping the resource.
        session_factory = self.replay_flight_data("filter-no-metrics")

        p = self.load_policy(
            {
                "name": "test-metrics",
                "resource": "gcp.instance",
                "filters": [
                    {'type': 'metrics',
                    'name': 'compute.googleapis.com/instance/cpu/utilization',
                    'metric-key': 'metric.labels.instance_name',
                    'aligner': 'ALIGN_MEAN',
                    'days': 14,
                    'value': 1,
                    'missing-value': 0,
                    'filter': ' resource.labels.zone = "us-east4-c"',
                    'op': 'less-than'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_batch_resources(self):
        policy = self.load_policy({
            "name": "test_batch_resources",
            "resource": "gcp.instance"})

        metric_filter = GCPMetricsFilter({'type': 'metrics',
                    'name': 'compute.googleapis.com/instance/cpu/utilization',
                    'metric-key': 'metric.labels.instance_name',
                    'value': .1,
                    'filter': ' resource.labels.zone = "us-east4-d"',
                    'op': 'less-than'}, manager=policy.resource_manager)
        resources = [{
            "name": "test_very_long_name"
        }] * 300
        metric_filter.process([])
        batch = metric_filter.get_batched_query_filter(resources)

        self.assertEqual(len(batch), 2)
        self.assertLess(len(batch[0]), 11000)
        self.assertIn('resource.labels.zone = "us-east4-d"', batch[0])
        self.assertIn('metric.type = "compute.googleapis.com/instance/cpu/utilization"', batch[0])
        self.assertIn('resource.labels.zone = "us-east4-d"', batch[1])
        self.assertIn('metric.type = "compute.googleapis.com/instance/cpu/utilization"', batch[1])

    def test_get_metric_resource_name_spanner_instance(self):
        # The `GCPMetricsFilter` made some assumptions about a method that
        # wasn't previously universally present: `get_metric_resource_name`.
        session_factory = self.replay_flight_data("filter-metrics-resource-name")
        p = self.load_policy(
            {
                "name": "test-metrics-resource-name",
                "resource": "gcp.spanner-instance",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "spanner.googleapis.com/instance/cpu/utilization",
                        "days": 14,
                        "op": "lte",
                        "value": 0.05,
                        "aligner": "ALIGN_MEAN",
                    },
                ],
            },
            session_factory=session_factory,
        )

        resources = p.run()
        # This should be filtering out the resource, & not erroring..
        self.assertEqual(len(resources), 0)

    def test_metrics_period_start_start_of_day(self):
        """
        Ensure GCPMetricsFilter correctly snaps the metric window to full UTC
        calendar days when 'period-start' is set to "start-of-day".

        This verifies:
        - start aligns to 00:00:00 UTC N days ago
        - end aligns to 00:00:00 UTC of the current day
        - period equals the exact difference between start and end
        """

        policy = self.load_policy(
            {
                "name": "gcp-period-start-test",
                "resource": "gcp.instance",
                "filters": [
                    {
                        "type": "metrics",
                        "name": "compute.googleapis.com/instance/cpu/utilization",
                        "metric-key": "metric.labels.instance_name",
                        "aligner": "ALIGN_MEAN",
                        "days": 2,
                        "period-start": "start-of-day",
                        "value": 0.1,
                        "filter": 'resource.labels.zone = "us-east4-c"',
                        "op": "less-than",
                    }
                ],
            },
        )

        metrics_filter = policy.resource_manager.filters[0]

        metrics_filter.process([])

        # Start should be midnight UTC
        self.assertEqual(metrics_filter.start.hour, 0)
        self.assertEqual(metrics_filter.start.minute, 0)
        self.assertEqual(metrics_filter.start.second, 0)
        self.assertEqual(metrics_filter.start.microsecond, 0)

        # End should now be midnight UTC
        self.assertEqual(metrics_filter.end.hour, 0)
        self.assertEqual(metrics_filter.end.minute, 0)
        self.assertEqual(metrics_filter.end.second, 0)
        self.assertEqual(metrics_filter.end.microsecond, 0)

        # Period should match the difference in seconds
        expected_period = (metrics_filter.end - metrics_filter.start).total_seconds()
        actual_period = float(metrics_filter.period.rstrip("s"))
        self.assertEqual(actual_period, expected_period)

    def _metric_filter(self, **overrides):
        # gcp.instance supplies metric_key, so a policy need not set metric-key.
        policy = self.load_policy({
            "name": "test_distribution_value",
            "resource": "gcp.instance"})
        data = {
            'type': 'metrics',
            'name': 'aiplatform.googleapis.com/tuned_model/online_serving/tokens',
            'value': 10.0,
            'op': 'equal'}
        data.update(overrides)
        return GCPMetricsFilter(data, manager=policy.resource_manager)

    def _process_resource(self, metric_filter, points):
        # process([]) sets up self.* attributes (distribution, op, etc.) without
        # making any API call, since batch_resources([]) short-circuits to [].
        # See test_batch_resources above for the same pattern.
        metric_filter.process([])
        resource = {"name": "test-instance"}
        resource_name = metric_filter.manager.resource_type.get_metric_resource_name(
            resource, metric_key=metric_filter.metric_key)
        metric_filter.resource_metric_dict[resource_name] = {"points": points}
        return metric_filter.process_resource(resource)

    def test_distribution_default_sum(self):
        # A Distribution carries no total, so count * mean reconstructs one:
        # count=4, mean=2.5 is 10.0.
        metric_filter = self._metric_filter()
        points = [{"value": {"distributionValue": {"count": "4", "mean": 2.5}}}]
        self.assertTrue(self._process_resource(metric_filter, points))

    def test_distribution_count(self):
        metric_filter = self._metric_filter(distribution='count', value=4)
        points = [{"value": {"distributionValue": {"count": "4", "mean": 2.5}}}]
        self.assertTrue(self._process_resource(metric_filter, points))
        # count arrives as the int64 string the API sends, and comes back an int.
        self.assertIsInstance(metric_filter.get_point_value(points[0]["value"]), int)

    def test_distribution_mean(self):
        metric_filter = self._metric_filter(distribution='mean', value=2.5)
        points = [{"value": {"distributionValue": {"count": "4", "mean": 2.5}}}]
        self.assertTrue(self._process_resource(metric_filter, points))

    def test_distribution_no_samples(self):
        # Proto3 JSON drops a field set to its default, so an alignment period
        # that recorded no samples arrives with neither count nor mean.
        metric_filter = self._metric_filter(distribution='mean', value=0)
        points = [{"value": {"distributionValue": {}}}]
        self.assertTrue(self._process_resource(metric_filter, points))

    def test_distribution_count_no_samples(self):
        # The same omission on the count branch, with the bucket payload the
        # API really sends alongside it.
        metric_filter = self._metric_filter(distribution='count', value=0)
        points = [{"value": {"distributionValue": {
            "bucketOptions": {"exponentialBuckets": {
                "numFiniteBuckets": 17, "growthFactor": 2, "scale": 1}}}}}]
        self.assertTrue(self._process_resource(metric_filter, points))

    def test_distribution_ignored_for_scalar_metric(self):
        # The key only reduces a histogram. A scalar point is read as before.
        metric_filter = self._metric_filter(distribution='count', value=10.0)
        points = [{"value": {"int64Value": "10"}}]
        self.assertTrue(self._process_resource(metric_filter, points))

    def test_scalar_reads_most_recent_point_only(self):
        # Monitoring returns points newest first, and the default ALIGN_NONE
        # returns every raw sample. Only the newest is compared, not the total.
        metric_filter = self._metric_filter(value=10.0)
        points = [
            {"value": {"int64Value": "10"}},
            {"value": {"int64Value": "20"}},
            {"value": {"int64Value": "5"}},
        ]
        self.assertTrue(self._process_resource(metric_filter, points))

    def test_distribution_reads_most_recent_point_only(self):
        metric_filter = self._metric_filter(value=6.0)
        points = [
            {"value": {"distributionValue": {"count": "2", "mean": 3.0}}},
            {"value": {"distributionValue": {"count": "1", "mean": 4.0}}},
        ]
        self.assertTrue(self._process_resource(metric_filter, points))

    def _distribution_policy(self, distribution):
        return {
            "name": "test_distribution_schema",
            "resource": "gcp.instance",
            "filters": [{
                "type": "metrics",
                "name": "aiplatform.googleapis.com/tuned_model/online_serving/tokens",
                "distribution": distribution,
                "value": 10,
                "op": "greater-than"}]}

    def test_distribution_schema_accepts_enum(self):
        # Asserts the schema key and the attribute agree, which is what a
        # misspelling on either side would break.
        policy = self.load_policy(self._distribution_policy("mean"))
        metric_filter = policy.resource_manager.filters[0]
        metric_filter.process([])
        self.assertEqual(metric_filter.distribution, "mean")

    def test_distribution_schema_rejects_other_values(self):
        with self.assertRaises(PolicyValidationError):
            self.load_policy(self._distribution_policy("median"))

    def test_multiple_timeseries_per_resource_raises(self):
        # A metric label such as type=input/output splits one resource across
        # several series, and picking one of them is the policy author's call.
        metric_filter = self._metric_filter()
        metric_filter.process([])
        series = [
            {"metric": {"labels": {"instance_name": "test-instance", "type": "input"}},
             "points": [{"value": {"distributionValue": {"count": "5", "mean": 7.0}}}]},
            {"metric": {"labels": {"instance_name": "test-instance", "type": "output"}},
             "resource": {"labels": {"zone": "us-central1-a"}},
             "points": [{"value": {"distributionValue": {"count": "5", "mean": 49.6}}}]},
        ]
        with self.assertRaises(PolicyExecutionError) as cm:
            metric_filter.split_by_resource(series)
        message = str(cm.exception)
        self.assertIn("multiple timeSeries for test-instance", message)
        # The labels name what split the series, so the author knows what to
        # group by. Both label sets are reported, not just metric.labels.
        self.assertIn("type", message)
        self.assertIn("zone", message)

    def test_unresolved_metric_key_series_are_skipped(self):
        # jmespath returns None when metric-key matches nothing in the series.
        # Two of those are not one resource twice, and must not abort the policy.
        metric_filter = self._metric_filter()
        metric_filter.process([])
        point = {"value": {"distributionValue": {"count": "5", "mean": 7.0}}}
        series = [
            {"metric": {"labels": {"type": "input"}}, "points": [point]},
            {"metric": {"labels": {"type": "output"}}, "points": [point]},
        ]
        metric_filter.split_by_resource(series)
        self.assertEqual(metric_filter.resource_metric_dict, {})


class TestSecurityComandCenterFindingsFilter(BaseTest):

    def test_findings(self):

        session_factory = self.replay_flight_data("filter-scc-findings")

        p = self.load_policy(
            {
                "name": "test-scc-findings",
                "resource": "gcp.bucket",
                "filters": [
                    {'type': 'scc-findings',
                     'org': 111111111111,
                     'key': 'category',
                     'value': 'BUCKET_LOGGING_DISABLED'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:matched-findings'][0]['category'],
          'BUCKET_LOGGING_DISABLED')

    def test_findings_no_key(self):

        session_factory = self.replay_flight_data("filter-scc-findings")

        p = self.load_policy(
            {
                "name": "test-scc-findings",
                "resource": "gcp.bucket",
                "filters": [
                    {'type': 'scc-findings',
                     'org': 111111111111}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)


class TestAlertsFilter(BaseTest):

    def test_metric_has_alert(self):

        session_factory = self.replay_flight_data("filter-alerts")

        p = self.load_policy(
            {
                "name": "test-alerts",
                "resource": "gcp.log-project-metric",
                "filters": [{
                    'type': 'value',
                    'key': 'name',
                    'value': 'test-metric-1'},
                    {'type': 'alerts'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_metric_has_no_alert(self):

        session_factory = self.replay_flight_data("filter-alerts")

        p = self.load_policy(
            {
                "name": "test-alerts",
                "resource": "gcp.log-project-metric",
                "filters": [{
                    'type': 'value',
                    'key': 'name',
                    'value': 'test-metric-2'},
                    {'type': 'alerts'}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_alert_on_invalid_resource(self):

        with self.assertRaises(PolicyValidationError):
            self.load_policy(
                {
                    "name": "test-alerts",
                    "resource": "gcp.bucket",
                    "filters": [{
                        'type': 'value',
                        'key': 'name',
                        'value': 'some-bucket'},
                        {'type': 'alerts'}],
                })
