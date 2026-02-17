# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Monitoring Metrics suppport for resources
"""
from datetime import datetime, timedelta

from c7n.filters.core import Filter, OPERATORS, FilterValidationError
from c7n.filters.metrics import METRIC_WINDOW_ALIGNMENT
from c7n.utils import local_session, type_schema, jmespath_search, snap_to_period_start

from c7n_gcp.provider import resources as gcp_resources

REDUCERS = [
    'REDUCE_NONE',
    'REDUCE_MEAN',
    'REDUCE_MIN',
    'REDUCE_MAX',
    'REDUCE_MEAN',
    'REDUCE_SUM',
    'REDUCE_STDDEV',
    'REDUCE_COUNT',
    'REDUCE_COUNT_TRUE',
    'REDUCE_COUNT_FALSE',
    'REDUCE_FRACTION_TRUE',
    'REDUCE_PERCENTILE_99',
    'REDUCE_PERCENTILE_95',
    'REDUCE_PERCENTILE_50',
    'REDUCE_PERCENTILE_05']

ALIGNERS = [
    'ALIGN_NONE',
    'ALIGN_DELTA',
    'ALIGN_RATE',
    'ALIGN_INTERPOLATE',
    'ALIGN_MIN',
    'ALIGN_MAX',
    'ALIGN_MEAN',
    'ALIGN_COUNT',
    'ALIGN_SUM',
    'REDUCE_COUNT_FALSE',
    'ALIGN_STDDEV',
    'ALIGN_COUNT_TRUE',
    'ALIGN_COUNT_FALSE',
    'ALIGN_FRACTION_TRUE',
    'ALIGN_PERCENTILE_99',
    'ALIGN_PERCENTILE_95',
    'ALIGN_PERCENTILE_50',
    'ALIGN_PERCENTILE_05',
    'ALIGN_PERCENT_CHANG']

BATCH_SIZE = 10000


class GCPMetricsFilter(Filter):
    """Supports metrics filters on resources.

    All resources that have cloud watch metrics are supported.

    Docs on cloud watch metrics

    - Google Supported Metrics
      https://cloud.google.com/monitoring/api/metrics_gcp

    - Custom Metrics
      https://cloud.google.com/monitoring/api/v3/metric-model#intro-custom-metrics

    .. code-block:: yaml

      - name: firewall-hit-count
        resource: gcp.firewall
        filters:
          - type: metrics
            name: firewallinsights.googleapis.com/subnet/firewall_hit_count
            aligner: ALIGN_COUNT
            days: 14
            value: 1
            op: greater-than

    The ``period-start`` key allows you to align the metric window in two ways.
    By default, using ``auto``, the window is computed relative to the current time.
    Alternatively, setting it to ``start-of-day`` aligns the window to full UTC calendar days,
    beginning at 00:00:00 UTC and ending at 23:59:59 UTC.

    .. code-block:: yaml

      - name: instance-low-cpu-last-full-day
        resource: gcp.instance
        filters:
          - type: metrics
            name: compute.googleapis.com/instance/cpu/utilization
            aligner: ALIGN_MEAN
            days: 1
            value: 0.05
            op: less-than
            period-start: start-of-day
    """

    schema = type_schema(
        'metrics',
        **{'name': {'type': 'string'},
          'metric-key': {'type': 'string'},
          'group-by-fields': {'type': 'array', 'items': {'type': 'string'}},
          'days': {'type': 'number'},
          'period-start': {'type': 'string', 'enum': METRIC_WINDOW_ALIGNMENT},
          'op': {'type': 'string', 'enum': list(OPERATORS.keys())},
          'reducer': {'type': 'string', 'enum': REDUCERS},
          'aligner': {'type': 'string', 'enum': ALIGNERS},
          'value': {'type': 'number'},
          'filter': {'type': 'string'},
          'missing-value': {'type': 'number'},
          'required': ('value', 'name', 'op')})
    permissions = ("monitoring.timeSeries.list",)

    def validate(self):
        if not self.data.get('metric-key') and \
           not hasattr(self.manager.resource_type, 'metric_key'):
            raise FilterValidationError("metric-key not defined for resource %s,"
            "so must be provided in the policy" % (self.manager.type))
        return self

    def process(self, resources, event=None):
        days = self.data.get('days', 14)
        duration = timedelta(days)

        self.metric = self.data['name']
        self.metric_key = self.data.get('metric-key') or self.manager.resource_type.metric_key
        self.aligner = self.data.get('aligner', 'ALIGN_NONE')
        self.reducer = self.data.get('reducer', 'REDUCE_NONE')
        self.group_by_fields = self.data.get('group-by-fields', [])
        self.missing_value = self.data.get('missing-value')

        self.end = datetime.utcnow().replace(microsecond=0)
        self.start = self.end - duration
        self.period_start = self.data.get('period-start', 'auto')
        self.start, self.end = snap_to_period_start(self.start, self.end, self.period_start)

        self.period = str((self.end - self.start).total_seconds()) + 's'
        self.resource_metric_dict = {}
        self.op = OPERATORS[self.data.get('op', 'less-than')]
        self.value = self.data['value']
        self.filter = self.data.get('filter', '')
        self.c7n_metric_key = "%s.%s.%s" % (self.metric, self.aligner, self.reducer)

        session = local_session(self.manager.session_factory)
        client = session.client("monitoring", "v3", "projects.timeSeries")
        project = session.get_default_project()

        time_series_data = []
        for batched_filter in self.get_batched_query_filter(resources):
            query_params = {
                'filter': batched_filter,
                'interval_startTime': self.start.isoformat() + 'Z',
                'interval_endTime': self.end.isoformat() + 'Z',
                'aggregation_alignmentPeriod': self.period,
                "aggregation_perSeriesAligner": self.aligner,
                "aggregation_crossSeriesReducer": self.reducer,
                "aggregation_groupByFields": self.group_by_fields,
                'view': 'FULL'
            }
            metric_list = client.execute_query('list',
                {'name': 'projects/' + project, **query_params})
            time_series_data.extend(metric_list.get('timeSeries', []))

        if not time_series_data:
            self.log.info("No metrics found for {}".format(self.c7n_metric_key))
            return []

        self.split_by_resource(time_series_data)
        matched = [r for r in resources if self.process_resource(r)]

        return matched

    def batch_resources(self, resources):
        if not resources:
            return []

        batched_resources = []

        resource_filter = []
        batch_size = len(self.filter)
        for r in resources:
            resource_name = self.manager.resource_type.get_metric_resource_name(
                r, metric_key=self.metric_key)
            resource_filter_item = '{} = "{}"'.format(self.metric_key, resource_name)
            resource_filter.append(resource_filter_item)
            resource_filter.append(' OR ')
            batch_size += len(resource_filter_item) + 4
            if batch_size >= BATCH_SIZE:
                resource_filter.pop()
                batched_resources.append(resource_filter)
                resource_filter = []
                batch_size = len(self.filter)

        resource_filter.pop()
        batched_resources.append(resource_filter)
        return batched_resources

    def get_batched_query_filter(self, resources):
        batched_filters = []
        metric_filter_type = 'metric.type = "{}" AND ( '.format(self.metric)
        user_filter = ''
        if self.filter:
            user_filter = " AND " + self.filter

        for batch in self.batch_resources(resources):
            batched_filters.append(''.join([
                metric_filter_type,
                ''.join(batch),
                ' ) ',
                user_filter
            ]))
        return batched_filters

    def split_by_resource(self, metric_list):
        for m in metric_list:
            resource_name = jmespath_search(self.metric_key, m)
            self.resource_metric_dict[resource_name] = m

    def process_resource(self, resource):
        resource_metric = resource.setdefault('c7n.metrics', {})
        resource_name = self.manager.resource_type.get_metric_resource_name(
            resource, metric_key=self.metric_key)
        metric = self.resource_metric_dict.get(resource_name)
        if not metric and not self.missing_value:
            return False
        if not metric:
            metric_value = self.missing_value
        else:
            metric_value = float(list(metric["points"][0]["value"].values())[0])

        resource_metric[self.c7n_metric_key] = metric

        matched = self.op(metric_value, self.value)
        return matched

    @classmethod
    def register_resources(klass, registry, resource_class):
        if resource_class.filter_registry:
            if resource_class.resource_type.allow_metrics_filters:
                resource_class.filter_registry.register('metrics', klass)


gcp_resources.subscribe(GCPMetricsFilter.register_resources)
