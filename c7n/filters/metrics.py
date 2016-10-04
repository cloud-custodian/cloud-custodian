# Copyright 2016 Capital One Services, LLC
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

TODO make filters package
  - offhours
  - metrics
  -
"""
from concurrent.futures import as_completed
from datetime import datetime, timedelta

from c7n.filters import Filter, OPERATORS
from c7n.utils import local_session, type_schema, chunks


class MetricsFilter(Filter):
    """Supports cloud watch metrics filters on resources.

    Docs on cloud watch metrics

    - GetMetricStatistics - http://goo.gl/w8mMEY
    - Supported Metrics - http://goo.gl/n0E0L7

    usage:: yaml

      - name: ec2-underutilized
        resource: ec2
        filters:
          - type: metric
            name: CPUUtilization
            days: 4
            period: 86400
            value: 30
            op: less-than

    Note periods when a resource is not sending metrics are not part
    of calculated statistics as in the case of a stopped ec2 instance,
    nor for resources to new to have existed the entire
    period. ie. being stopped for an ec2 intsance wouldn't lower the
    average cpu utilization, nor would

    Todo

      - support offhours considerations (just run at night?)
      - support additional stats, values

    Use Case / Find Underutilized servers non-inclusive of offhour periods

      If server has no data for period, its omitted.

      So a server that's off reports no metrics for the relevant period.

    """

    schema = type_schema(
        'metrics',
        namespace={'type': 'string'},
        name={'type': 'string'},
        dimensions={'type': 'array', 'items': {'type': 'string'}},
        # Type choices
        statistics={'type': 'string', 'enum': [
            'Average', 'Sum', 'Maximum', 'Minimum', 'SampleCount']},
        days={'type': 'number'},
        op={'type': 'string', 'enum': OPERATORS.keys()},
        value={'type': 'number'},
        required=('value', 'name'))

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
            ns = getattr(self.model, 'default_namespace', None)
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
            r['Metrics'] = client.get_metric_statistics(
                Namespace=self.namespace,
                MetricName=self.metric,
                Statistics=[self.statistics],
                StartTime=self.start,
                EndTime=self.end,
                Period=self.period,
                Dimensions=dimensions)['Datapoints']
            if len(r['Metrics']) == 0:
                continue
            if self.op(r['Metrics'][0][self.statistics], self.value):
                matched.append(r)
        return matched
