# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
CloudWatch Metrics suppport for resources
"""
import re

from collections import namedtuple
from concurrent.futures import as_completed
from datetime import datetime, timedelta

from c7n.exceptions import PolicyValidationError
from c7n.filters.core import Filter, OPERATORS
from c7n.utils import local_session, type_schema, chunks, snap_to_period_start

METRIC_WINDOW_ALIGNMENT = [
    'auto',
    'start-of-day']


class MetricsFilter(Filter):
    """Supports cloud watch metrics filters on resources.

    All resources that have cloud watch metrics are supported.

    Docs on cloud watch metrics

    - GetMetricStatistics
      https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricStatistics.html

    - Supported Metrics
      https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/aws-services-cloudwatch-metrics.html

    .. code-block:: yaml

      - name: ec2-underutilized
        resource: ec2
        filters:
          - type: metrics
            name: CPUUtilization
            days: 4
            period: 86400
            value: 30
            op: less-than

    Note periods when a resource is not sending metrics are not part
    of calculated statistics as in the case of a stopped ec2 instance,
    nor for resources to new to have existed the entire
    period. ie. being stopped for an ec2 instance wouldn't lower the
    average cpu utilization.

    The "missing-value" key allows a policy to specify a default
    value when CloudWatch has no data to report:

    .. code-block:: yaml

      - name: elb-low-request-count
        resource: elb
        filters:
          - type: metrics
            name: RequestCount
            statistics: Sum
            days: 7
            value: 7
            missing-value: 0
            op: less-than

    This policy matches any ELB with fewer than 7 requests for the past week.
    ELBs with no requests during that time will have an empty set of metrics.
    Rather than skipping those resources, "missing-value: 0" causes the
    policy to treat their request counts as 0.

    Note the default statistic for metrics is Average.

    The ``period-start`` key allows you to align the metric window in two ways.
    By default, using ``auto``, the window is computed relative to the current time.
    Alternatively, setting it to ``start-of-day`` aligns the window to full UTC calendar days,
    beginning at 00:00:00 UTC and ending at current day 00:00:00 UTC.

    .. code-block:: yaml

      - name: ec2-low-cpu-last-full-day
        resource: ec2
        filters:
          - type: metrics
            name: CPUUtilization
            days: 1
            period: 86400
            value: 30
            op: less-than
            period-start: start-of-day
    """

    schema = type_schema(
        'metrics',
        **{'namespace': {'type': 'string'},
           'name': {'type': 'string'},
           'dimensions': {
               'type': 'object',
               'patternProperties': {
                   '^.*$': {'type': 'string'}}},
           # Type choices
           'statistics': {'type': 'string'},
           'days': {'type': 'number'},
           'period-start': {'type': 'string', 'enum': METRIC_WINDOW_ALIGNMENT},
           'op': {'type': 'string', 'enum': list(OPERATORS.keys())},
           'value': {'type': 'number'},
           'period': {'type': 'number'},
           'attr-multiplier': {'type': 'number'},
           'percent-attr': {'type': 'string'},
           'missing-value': {'type': 'number'},
           'required': ('value', 'name')})
    schema_alias = True
    permissions = ("cloudwatch:GetMetricStatistics",)

    MAX_QUERY_POINTS = 50850
    MAX_RESULT_POINTS = 1440

    # Default per service, for overloaded services like ec2
    # we do type specific default namespace annotation
    # specifically AWS/EBS and AWS/EC2Spot

    # ditto for spot fleet
    DEFAULT_NAMESPACE = {
        'apigateway': 'AWS/ApiGateway',
        'cloudfront': 'AWS/CloudFront',
        'cloudsearch': 'AWS/CloudSearch',
        'dynamodb': 'AWS/DynamoDB',
        'ecs': 'AWS/ECS',
        'ecr': 'AWS/ECR',
        'efs': 'AWS/EFS',
        'elasticache': 'AWS/ElastiCache',
        'ec2': 'AWS/EC2',
        'elb': 'AWS/ELB',
        'elbv2': 'AWS/ApplicationELB',
        'emr': 'AWS/ElasticMapReduce',
        'es': 'AWS/ES',
        'events': 'AWS/Events',
        'firehose': 'AWS/Firehose',
        'fsx': 'AWS/FSx',
        'kinesis': 'AWS/Kinesis',
        'lambda': 'AWS/Lambda',
        'logs': 'AWS/Logs',
        'redshift': 'AWS/Redshift',
        'rds': 'AWS/RDS',
        'route53': 'AWS/Route53',
        's3': 'AWS/S3',
        'sns': 'AWS/SNS',
        'sqs': 'AWS/SQS',
        'workspaces': 'AWS/WorkSpaces',
    }

    standard_stats = {'Average', 'Sum', 'Maximum', 'Minimum', 'SampleCount'}
    extended_stats_re = re.compile(r'^p\d{1,3}\.{0,1}\d{0,1}$')

    def __init__(self, data, manager=None):
        super(MetricsFilter, self).__init__(data, manager)
        self.days = self.data.get('days', 14)
        self.period_start = self.data.get('period-start', 'auto')

    def validate(self):
        stats = self.data.get('statistics', 'Average')
        if stats not in self.standard_stats and not self.extended_stats_re.match(stats):
            raise PolicyValidationError(
                "metrics filter statistics method %s not supported" % stats)

        if self.days > 455:
            raise PolicyValidationError(
                "metrics filter days value (%s) cannot exceed 455" % self.days)

    def get_metric_window(self):
        """Determine start and end times for the CloudWatch metric window

        Ensure that the window aligns with time segments based on CloudWatch's retention
        schedule defined here:

        https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_concepts.html#Metric
        """  # noqa: E501

        duration = timedelta(self.days)
        now = datetime.utcnow()
        MetricWindow = namedtuple('MetricWindow', 'start end')

        if duration <= timedelta(days=(1 / 8.0)):
            # Align period with the start of the next second
            # CloudWatch retention: 3 hours
            end = now.replace(microsecond=0) + timedelta(seconds=1)
        elif duration <= timedelta(days=15):
            # Align period with the start of the next minute
            # CloudWatch retention: 15 days
            end = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        elif duration <= timedelta(days=63):
            # Align period with the start of the next five-minute block
            # CloudWatch retention: 63 days
            end = (now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
                + timedelta(minutes=5))
        else:
            # Align period with the start of the next hour
            # CloudWatch retention: 455 days
            end = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        start = end - duration

        start, end = snap_to_period_start(start, end, self.period_start)

        return MetricWindow(start, end)

    def process(self, resources, event=None):
        self.start, self.end = self.get_metric_window()
        self.metric = self.data['name']
        self.period = int(self.data.get('period', (self.end - self.start).total_seconds()))
        self.statistics = self.data.get('statistics', 'Average')
        self.model = self.manager.get_model()
        self.op = OPERATORS[self.data.get('op', 'less-than')]
        self.value = self.data['value']

        ns = self.data.get('namespace')
        if not ns:
            ns = getattr(self.model, 'metrics_namespace', None)
            if not ns:
                ns = self.DEFAULT_NAMESPACE[self.model.service]
        self.namespace = ns

        self.log.debug("Querying metrics for %d", len(resources))
        matched = []
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for resource_set in chunks(resources, 50):
                futures.append(
                    w.submit(self.process_resource_set, resource_set))

            for f in as_completed(futures):
                if f.exception():
                    self.log.warning(
                        "CW Retrieval error: %s" % f.exception())
                    continue
                matched.extend(f.result())
        return matched

    def get_dimensions(self, resource):
        return [{'Name': self.model.dimension,
                 'Value': resource[self.model.dimension]}]

    def get_user_dimensions(self):
        dims = []
        if 'dimensions' not in self.data:
            return dims
        for k, v in self.data['dimensions'].items():
            dims.append({'Name': k, 'Value': v})
        return dims

    def process_resource_set(self, resource_set):
        client = local_session(
            self.manager.session_factory).client('cloudwatch')

        matched = []
        for r in resource_set:
            # if we overload dimensions with multiple resources we get
            # the statistics/average over those resources.
            dimensions = self.get_dimensions(r)
            # Merge in any filter specified metrics, get_dimensions is
            # commonly overridden so we can't do it there.
            dimensions.extend(self.get_user_dimensions())

            collected_metrics = r.setdefault('c7n.metrics', {})
            # Note this annotation cache is policy scoped, not across
            # policies, still the lack of full qualification on the key
            # means multiple filters within a policy using the same metric
            # across different periods or dimensions would be problematic.
            key = "%s.%s.%s.%s" % (self.namespace, self.metric, self.statistics, str(self.days))

            params = dict(
                Namespace=self.namespace,
                MetricName=self.metric,
                StartTime=self.start,
                EndTime=self.end,
                Period=self.period,
                Dimensions=dimensions
            )

            stats_key = (self.statistics in self.standard_stats
                         and 'Statistics' or 'ExtendedStatistics')
            params[stats_key] = [self.statistics]

            if key not in collected_metrics:
                collected_metrics[key] = client.get_metric_statistics(
                    **params)['Datapoints']

            # In certain cases CloudWatch reports no data for a metric.
            # If the policy specifies a fill value for missing data, add
            # that here before testing for matches. Otherwise, skip
            # matching entirely.
            if len(collected_metrics[key]) == 0:
                if 'missing-value' not in self.data:
                    continue
                collected_metrics[key].append({
                    'Timestamp': self.start,
                    self.statistics: self.data['missing-value'],
                    'c7n:detail': 'Fill value for missing data'
                })

            if self.data.get('percent-attr'):
                rvalue = r[self.data.get('percent-attr')]
                if self.data.get('attr-multiplier'):
                    rvalue = rvalue * self.data['attr-multiplier']
                all_meet_condition = True
                for data_point in collected_metrics[key]:
                    percent = (data_point[self.statistics] / rvalue * 100)
                    if not self.op(percent, self.value):
                        all_meet_condition = False
                        break
                if all_meet_condition:
                    matched.append(r)
            else:
                all_meet_condition = True
                for data_point in collected_metrics[key]:
                    if 'ExtendedStatistics' in data_point:
                        data_point = data_point['ExtendedStatistics']
                    if not self.op(data_point[self.statistics], self.value):
                        all_meet_condition = False
                        break
                if all_meet_condition:
                    matched.append(r)
        return matched


class ShieldMetrics(MetricsFilter):
    """Specialized metrics filter for shield
    """
    schema = type_schema('shield-metrics', rinherit=MetricsFilter.schema)

    namespace = "AWS/DDoSProtection"
    metrics = (
        'DDoSAttackBitsPerSecond',
        'DDoSAttackRequestsPerSecond',
        'DDoSDetected')

    attack_vectors = (
        'ACKFlood',
        'ChargenReflection',
        'DNSReflection',
        'GenericUDPReflection',
        'MSSQLReflection',
        'NetBIOSReflection',
        'NTPReflection',
        'PortMapper',
        'RequestFlood',
        'RIPReflection',
        'SNMPReflection',
        'SYNFlood',
        'SSDPReflection',
        'UDPTraffic',
        'UDPFragment')

    def validate(self):
        if self.data.get('name') not in self.metrics:
            raise PolicyValidationError(
                "invalid shield metric %s valid:%s on %s" % (
                    self.data['name'],
                    ", ".join(self.metrics),
                    self.manager.data))

    def get_dimensions(self, resource):
        return [{
            'Name': 'ResourceArn',
            'Value': self.manager.get_arns([resource])[0]}]

    def process(self, resources, event=None):
        self.data['namespace'] = self.namespace
        return super(ShieldMetrics, self).process(resources, event)
