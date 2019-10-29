# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Copyright 2019 Hulu LLC. All Rights Reserved.
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
from __future__ import absolute_import, division, print_function, unicode_literals

import re

from concurrent.futures import as_completed
from datetime import timedelta, datetime
from statistics import mean

from c7n.filters import ValueFilter
from c7n.filters.metrics import MetricsFilter
from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema, get_retry


@resources.register('service-quota')
class ServiceQuota(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'service-quotas'
        enum_spec = ('list_services', 'Services', None)
        id = 'QuotaCode'
        arn = 'QuotaArn'
        name = 'QuotaName'
        metrics_namespace = 'AWS/Usage'

    def augment(self, resources):
        client = local_session(self.session_factory).client('service-quotas')
        retry = get_retry(('TooManyRequestsException',))

        def get_quotas(client, s):
            quotas = {}
            token = None
            kwargs = {
                'ServiceCode': s['ServiceCode'],
            }
            while True:
                if token:
                    kwargs['NextToken'] = token
                response = retry(
                    client.list_service_quotas,
                    **kwargs
                )
                rquotas = {q['QuotaCode']: q for q in response['Quotas']}
                token = response.get('NextToken')
                new = set(rquotas) - set(quotas)
                quotas.update(rquotas)
                if token is None:
                    break
                # ssm, ec2, kms have bad behaviors.
                elif token and not new:
                    break

            return quotas.values()

        results = []
        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for r in resources:
                futures[w.submit(get_quotas, client, r)] = r

            for f in as_completed(futures):
                if f.exception():
                    raise f.exception()
                results.extend(f.result())

        return results


@ServiceQuota.filter_registry.register('usage-metric')
class UsageFilter(MetricsFilter):
    """
    Filter service quotas by usage, only compatible with service quotas
    that return a UsageMetric attribute.

    Default limit is 80%

    .. code-block:: yaml

        policies:
            - name: service-quota-usage-limit
              description: |
                  find any services that have usage stats of
                  over 80%
              resource: aws.service-quota
              filters:
                - UsageMetric: present
                - type: usage-metric
                  limit: 19
    """

    schema = type_schema('usage-metric', limit={'type': 'integer'})

    permisisons = ('cloudwatch:GetMetricStatistics',)

    annotation_key = 'c7n:UsageMetric'

    time_delta_map = {
        'MICROSECOND': 'microseconds',
        'MILLISECOND': 'milliseconds',
        'SECOND': 'seconds',
        'MINUTE': 'minutes',
        'HOUR': 'hours',
        'DAY': 'days',
        'WEEK': 'weeks',
    }

    metric_map = {
        'Maximum': max,
        'Minimum': min,
        'Average': mean,
        'Sum': sum,
        'SampleCount': len
    }

    percentile_regex = re.compile('p\\d{0,2}\\.{0,1}\\d{0,2}')

    def get_dimensions(self, usage_metric):
        dimensions = []
        for k, v in usage_metric['MetricDimensions'].items():
            dimensions.append({'Name': k, 'Value': v})
        return dimensions

    def process(self, resources, event):
        client = local_session(self.manager.session_factory).client('cloudwatch')

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(1)

        limit = self.data.get('limit', 80)

        result = []

        for r in resources:
            metric = r.get('UsageMetric')
            if not metric:
                continue
            stat = metric.get('MetricStatisticRecommendation', 'Maximum')
            if stat not in self.metric_map and self.percentile_regex.match(stat) is None:
                continue
            if 'Period' in r:
                period_unit = self.time_delta_map[r['Period']['PeriodUnit']]
                period = int(timedelta(**{period_unit: r['Period']['PeriodValue']}).total_seconds())
            else:
                period = int(timedelta(1).total_seconds())
            res = client.get_metric_statistics(
                Namespace=metric['MetricNamespace'],
                MetricName=metric['MetricName'],
                Dimensions=self.get_dimensions(metric),
                Statistics=[stat],
                StartTime=start_time,
                EndTime=end_time,
                Period=period,
            )
            if res['Datapoints']:
                if self.percentile_regex.match(stat):
                    # AWS CloudWatch supports percentile statistic as a statistic but
                    # when comparing against a dataset for service quotas we only care
                    # about maximum... Also note that is probably what we should do
                    # for all statistic types, but if the service quota API will return
                    # different preferred statistics, atm we will try to match that
                    op = self.metric_map['Maximum']
                else:
                    op = self.metric_map[stat]
                m = op([x[stat] for x in res['Datapoints']])
                if m > (limit / 100) * r['Value']:
                    r[self.annotation_key] = {
                        'metric': m,
                        'period': period,
                        'start_time': start_time,
                        'end_time': end_time,
                        'statistic': stat,
                        'limit': limit / 100 * r['Value'],
                        'quota': r['Value'],
                    }
                    result.append(r)
        return result


@ServiceQuota.filter_registry.register('history')
class History(ValueFilter):
    """
    Filter on historical requests for service quota increases

    .. code-block:: yaml

        policies:
            - name: service-quota-increase-history-filter
              resource: aws.service-quota
              filters:
                - type: history
    """

    schema = type_schema('history')

    permissions = ('servicequota:ListRequestedServiceQuotaChangeHistory',)
    annotation_key = 'c7n:ServiceQuotaChangeHistory'

    def process(self, resources, event):
        client = local_session(self.manager.session_factory).client('service-quotas')
        token = None
        results = []
        history = []
        while True:
            res = client.list_requested_service_quota_change_history()
            token = res.get('NextToken')
            history.extend(res['RequestedQuotas'])
            if token is None:
                break

        service_request_map = {}
        for h in history:
            service_request_map.setdefault(h['ServiceCode'], {})
            service_request_map[h['ServiceCode']].setdefault(h['QuotaCode'], [])
            service_request_map[h['ServiceCode']][h['QuotaCode']].append(h)

        for r in resources:
            service = r['ServiceCode']
            quota = r['QuotaCode']
            if service in service_request_map and quota in service_request_map[service]:
                r.setdefault(self.annotation_key, [])
                r[self.annotation_key] = service_request_map[service][quota]
                results.append(r)

        return results


@ServiceQuota.action_registry.register('request-increase')
class Increase(Action):

    schema = type_schema('increase')

    def process(self, resources):
        pass
