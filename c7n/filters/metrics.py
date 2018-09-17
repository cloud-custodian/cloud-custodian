# Copyright 2016-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
CloudWatch Metrics suppport for resources
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from concurrent.futures import as_completed
from datetime import datetime, timedelta

from c7n.exceptions import PolicyValidationError
from c7n.filters.core import Filter, OPERATORS
from c7n.utils import local_session, type_schema, chunks


class MetricsFilter(Filter):
    """Supports cloud watch metrics filters on resources.

    All resources that have cloud watch metrics are supported.

    Docs on cloud watch metrics

    - GetMetricStatistics - http://goo.gl/w8mMEY
    - Supported Metrics - http://goo.gl/n0E0L7

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
    average cpu utilization, nor would
    """

    schema = type_schema(
        'metrics',
        **{'namespace': {'type': 'string'},
           'name': {'type': 'string'},
           'dimensions': {'type': 'array', 'items': {'type': 'string'}},
           # Type choices
           'statistics': {'type': 'string', 'enum': [
               'Average', 'Sum', 'Maximum', 'Minimum', 'SampleCount']},
           'days': {'type': 'number'},
           'op': {'type': 'string', 'enum': list(OPERATORS.keys())},
           'value': {'type': 'number'},
           'period': {'type': 'number'},
           'attr-multiplier': {'type': 'number'},
           'percent-attr': {'type': 'string'},
           'required': ('value', 'name')})

    permissions = ("cloudwatch:GetMetricStatistics",)

    MAX_QUERY_POINTS = 50850
    MAX_RESULT_POINTS = 1440

    # Default per service, for overloaded services like ec2
    # we do type specific default namespace annotation
    # specifically AWS/EBS and AWS/EC2Spot

    # ditto for spot fleet
    DEFAULT_NAMESPACE = {
        'cloudfront': 'AWS/CloudFront',
        'cloudsearch': 'AWS/CloudSearch',
        'dynamodb': 'AWS/DynamoDB',
        'ecs': 'AWS/ECS',
        'elasticache': 'AWS/ElastiCache',
        'ec2': 'AWS/EC2',
        'elb': 'AWS/ELB',
        'elbv2': 'AWS/ApplicationELB',
        'emr': 'AWS/EMR',
        'es': 'AWS/ES',
        'events': 'AWS/Events',
        'firehose': 'AWS/Firehose',
        'kinesis': 'AWS/Kinesis',
        'lambda': 'AWS/Lambda',
        'logs': 'AWS/Logs',
        'redshift': 'AWS/Redshift',
        'rds': 'AWS/RDS',
        'route53': 'AWS/Route53',
        's3': 'AWS/S3',
        'sns': 'AWS/SNS',
        'sqs': 'AWS/SQS',
    }

    def process(self, resources, event=None):
        days = self.data.get('days', 14)
        duration = timedelta(days)

        self.metric = self.data['name']
        self.end = datetime.utcnow()
        self.start = self.end - duration
        self.period = int(self.data.get('period', duration.total_seconds()))
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

    def process_resource_set(self, resource_set):
        client = local_session(
            self.manager.session_factory).client('cloudwatch')

        matched = []
        for r in resource_set:
            # if we overload dimensions with multiple resources we get
            # the statistics/average over those resources.
            dimensions = self.get_dimensions(r)
            collected_metrics = r.setdefault('c7n.metrics', {})
            # Note this annotation cache is policy scoped, not across
            # policies, still the lack of full qualification on the key
            # means multiple filters within a policy using the same metric
            # across different periods or dimensions would be problematic.
            key = "%s.%s.%s" % (self.namespace, self.metric, self.statistics)
            if key not in collected_metrics:
                collected_metrics[key] = client.get_metric_statistics(
                    Namespace=self.namespace,
                    MetricName=self.metric,
                    Statistics=[self.statistics],
                    StartTime=self.start,
                    EndTime=self.end,
                    Period=self.period,
                    Dimensions=dimensions)['Datapoints']
            if len(collected_metrics[key]) == 0:
                continue
            if self.data.get('percent-attr'):
                rvalue = r[self.data.get('percent-attr')]
                if self.data.get('attr-multiplier'):
                    rvalue = rvalue * self.data['attr-multiplier']
                percent = (collected_metrics[key][0][self.statistics] /
                           rvalue * 100)
                if self.op(percent, self.value):
                    matched.append(r)
            elif self.op(collected_metrics[key][0][self.statistics], self.value):
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
            'Value': self.manager.get_arn(resource)}]

    def process(self, resources, event=None):
        self.data['namespace'] = self.namespace
        return super(ShieldMetrics, self).process(resources, event)
