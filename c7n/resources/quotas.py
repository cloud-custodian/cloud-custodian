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
import math

from concurrent.futures import as_completed
from datetime import timedelta, datetime
from statistics import mean

from c7n.actions import Action
from c7n.exceptions import PolicyExecutionError
from c7n.filters import Filter, ValueFilter
from c7n.filters.metrics import MetricsFilter
from c7n.filters.related import RelatedResourceFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema, get_retry


@resources.register('service-quota-request')
class ServiceQuotaRequest(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'service-quotas'
        enum_spec = ('list_requested_service_quota_change_history', 'RequestedQuotas', None)
        id = 'Id'
        arn = None
        name = None


@resources.register('service-quota')
class ServiceQuota(QueryResourceManager):

    batch_size = 100

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
                'MaxResults': self.batch_size
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
                - type: usage
                  limit: 19
    """

    schema = type_schema('usage', limit={'type': 'integer'})

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


@ServiceQuota.filter_registry.register('request-history')
class RequestHistoryFilter(RelatedResourceFilter):
    """
    Filter on historical requests for service quota increases

    .. code-block:: yaml

        policies:
            - name: service-quota-increase-history-filter
              resource: aws.service-quota
              filters:
                - type: request-history
                  key: '[].Status'
                  value: CASE_CLOSED
                  value_type: swap
                  op: in

    """

    RelatedResource = 'c7n.resources.quotas.ServiceQuotaRequest'
    RelatedIdsExpression = 'QuotaCode'
    AnnotationKey = 'ServiceQuotaChangeHistory'

    schema = type_schema(
        'request-history', rinherit=ValueFilter.schema
    )

    permissions = ('servicequota:ListRequestedServiceQuotaChangeHistory',)

    def get_related(self, resources):
        resource_manager = self.get_resource_manager()
        related_ids = self.get_related_ids(resources)
        related = resource_manager.resources()
        result = {}
        for r in related:
            result.setdefault(r[self.RelatedIdsExpression], [])
            if r[self.RelatedIdsExpression] in related_ids:
                result[r[self.RelatedIdsExpression]].append(r)
        return result

    def _add_annotations(self, related_ids, resource):
        resources = self.get_related([resource])
        a_resources = resources.get(resource[self.RelatedIdsExpression], [])
        akey = 'c7n:%s' % self.AnnotationKey
        resource[akey] = a_resources


@ServiceQuota.action_registry.register('request-increase')
class Increase(Action):
    """
    Request a limit increase for a service quota

    .. code-block:: yaml

        policies:
          - name: request-limit-increase
            resource: aws.service-quota
            filters:
              - type: value
                key: QuotaCode
                value: L-foo
            actions:
              - type: increase
                multiplier: 1.2
    """

    schema = type_schema('request-increase', multiplier={'type': 'number', 'minimum': 1.0})
    permissions = ('servicequota:RequestServiceQuotaIncrease',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('service-quotas')
        multiplier = self.data.get('multiplier', 1.2)
        error = None
        for r in resources:
            count = math.floor(multiplier * r['Value'])
            if not r['Adjustable']:
                continue
            try:
                client.request_service_quota_increase(
                    ServiceCode=r['ServiceCode'],
                    QuotaCode=r['QuotaCode'],
                    DesiredValue=count
                )
            except client.exceptions.QuotaExceededException as e:
                error = e
                self.log.error('Requested:%s exceeds quota limit for %s' % (count, r['QuotaCode']))
                continue
            except (client.exceptions.AccessDeniedException,
                    client.exceptions.DependencyAccessDeniedException,):
                raise PolicyExecutionError('Access Denied to increase quota: %s' % r['QuotaCode'])
            except (client.exceptions.NoSuchResourceException,
                    client.exceptions.InvalidResourceStateException,
                    client.exceptions.ResourceAlreadyExistsException,) as e:
                error = e
                continue
        if error:
            raise PolicyExecutionError from error


@ServiceQuota.action_registry.register('add-to-template')
class AddToTemplate(Action):
    """
    Adds service quota requests to template

    If no regions are specified, defaults to the current region

    Multiplier defaults to 1.2

    .. code-block:: yaml
        policies:
            - name: put-request-increase-in-template
              resource: aws.service-quota
              description: puts a quota increase request in template
              filters:
                - type: value
                  key: ServiceCode
                  value: ec2
                - type: value
                  key: QuotaName
                  value: *.On-Demand instances.*
                  op: regex
              actions:
                - type: add-to-template
                  regions:
                    - us-east-1
                    - us-west-2
                  multiplier: 1.2
    """

    all_regions = [
        'ap-northeast-1', 'ap-northeast-2', 'ap-south-1', 'ap-southeast-1', 'ap-southeast-2',
        'ca-central-1',
        'eu-central-1', 'eu-north-1', 'eu-west-1', 'eu-west-2', 'eu-west-3',
        'sa-east-1',
        'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2'
    ]

    schema = type_schema(
        'add-to-template',
        multiplier={'type': 'number'},
        regions={
            'type': 'array',
            'items': {
                'type': 'string', 'enum': all_regions
            }
        },
        **{'required': ['multiplier']}
    )
    permissions = ('servicequota:PutServiceQuotaIncreaseRequestIntoTemplate',)

    def process_resources(self, resources, op):
        # Use us-east-1 to make the request to get around the error:
        # TemplatesNotAvailableInRegionException
        # The Service Quotas template is not available in the Region where you
        # are making the request. Please make the request in us-east-1.
        # https://docs.aws.amazon.com/servicequotas/2019-06-24/apireference/API_PutServiceQuotaIncreaseRequestIntoTemplate.html

        session = local_session(self.manager.session_factory, region='us-east-1')
        client = session.client('service-quotas')

        regions = self.data.get('regions', [self.manager.region])

        multiplier = self.data.get('multiplier', 1.2)

        for r in resources:
            if not r['Adjustable']:
                continue
            kwargs = {
                'ServiceCode': r['ServiceCode'],
                'QuotaCode': r['QuotaCode'],
            }
            for region in regions:
                kwargs['AwsRegion'] = region
                if self.data['type'] == 'add-to-template':
                    kwargs['DesiredValue'] = math.floor(multiplier * r['Value'])
                try:
                    getattr(client, op)(**kwargs)
                except client.exceptions.AWSServiceAccessNotEnabledException:
                    raise PolicyExecutionError(
                        'Service Quota Template not associated with organization.')
                except client.exceptions.NoAvailableOrganizationException:
                    raise PolicyExecutionError('Account is not associated with an organization')
                except (client.exceptions.AccessDeniedException,
                        client.exceptions.DependencyAccessDeniedException,
                        client.exceptions.NoSuchResourceException):
                    continue

    def process(self, resources):
        op = 'put_service_quota_increase_request_into_template'
        self.process_resources(resources, op)


@ServiceQuota.action_registry.register('remove-from-template')
class RemoveFromTemplate(AddToTemplate):
    """
    Removes service quota requests from template

    If no regions are specified, defaults to the current region

    .. code-block:: yaml

        policies:
            - name: remove-service-quota-request-from-template
              resource: aws.service-quota
              description: remove quota increase request from template
              filters:
                - type: in-template
              actions:
                - type: remove-from-template
                  regions:
                    - us-east-1
                    - us-west-2
    """

    schema = type_schema(
        'remove-from-template',
        regions={
            'type': 'array',
            'items': {
                'type': 'string', 'enum': AddToTemplate.all_regions
            }
        }
    )

    permissions = ('servicequota:DeleteServiceQuotaIncreaseRequestFromTemplate',)

    def process(self, resources):
        op = 'delete_service_quota_increase_request_from_template'
        self.process_resources(resources, op)


@ServiceQuota.filter_registry.register('in-template')
class InTemplateFilter(Filter):
    """
    Filter if a service quota is in template

    .. code-block:: yaml

        policies:
          - name: in-template-check
            resource: aws.service-quota
            filters:
              - type: in-template
    """

    schema = type_schema(
        'in-template',
        quota={'type': 'string'},
        **{'properties': {'required': ['quota']}}
    )
    permissions = ('servicequota:ListServiceQuotaIncreaseRequestsInTemplate',)

    def process(self, resources, event):
        client = local_session(
            self.manager.session_factory, region='us-east-1'
        ).client('service-quotas')
        results = []
        requests = []
        token = ''
        while True:
            if token:
                res = client.list_service_quota_increase_requests_in_template(NextToken=token)
            else:
                res = client.list_service_quota_increase_requests_in_template()
            r = res['ServiceQuotaIncreaseRequestInTemplateList']
            requests.extend(r)
            if res.get('NextToken'):
                token = res['NextToken']
            else:
                break
        quotas = [r['QuotaCode'] for r in requests]
        for r in resources:
            if r['QuotaCode'] in quotas:
                results.append(r)
        return results
