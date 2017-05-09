# Copyright 2017 Capital One Services, LLC
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

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.filters import FilterRegistry, ValueFilter
from c7n.utils import local_session, type_schema
import re

filters = FilterRegistry('cloudtrail.filters')


@resources.register('cloudtrail')
class CloudTrail(QueryResourceManager):

    class resource_type(object):
        service = 'cloudtrail'
        enum_spec = ('describe_trails', 'trailList', None)
        #
        # detail_spec = (
        #    'get_event_selectors', 'TrailName', 'TrailArn', None)
        filter_name = 'trailNameList'
        filter_type = 'list'
        id = 'TrailArn'
        name = 'Name'
        dimension = None
        config_type = "AWS::CloudTrail::Trail"

    filter_registry = filters


@filters.register('monitored-metric')
class MonitoredCloudtrailMetric(ValueFilter):
    """Finds cloudtrails with logging and a metric filter. Is a subclass of ValueFilter,
    filtering the metric filter objects. Optionally, verifies an alarm exists (true by default),
    and for said alarm, there is atleast one SNS subscription (again, true by default).

    :example:

        .. code-block: yaml

            policies:
              - name: cloudtrail-trail-with-login-attempts
                resource: cloudtrail
                region: us-east-1
                filters:
                  - type: monitored-metric
                    alarm: true
                    topic-subscription: false
                    filter: '$.eventName = DeleteTrail'
    """

    schema = type_schema('monitored-metric', rinherit=ValueFilter.schema, **{
        'topic-subscription': {'type': 'boolean'},
        'alarm': {'type': 'boolean'}
    })

    permissions = ('logs:DescribeMetricFilters', 'cloudwatch:DescribeAlarms',
        'sns:ListSubscriptionsByTopic')

    def _filterTopicArnsToSubscribed(self, session, topicArns):
        sns = session.client('sns')

        def arnHasSubscriptions(arn):
            subscriptions = sns.list_subscriptions_by_topic(TopicArn=arn)['Subscriptions']
            return any(subscriptions)
        return filter(arnHasSubscriptions, topicArns)

    def _allAlarms(self, session):
        # TODO: We should cache this better.
        cloudwatch = session.client('cloudwatch')
        paginator = cloudwatch.get_paginator('describe_alarms')
        results = paginator.paginate().build_full_result()
        return results['MetricAlarms']

    def _metricFiltersForLogGroup(self, session, groupName):
        logs = session.client('logs')
        paginator = logs.get_paginator('describe_metric_filters')
        results = paginator.paginate(logGroupName=groupName).build_full_result()
        return results['metricFilters']

    def _alarmInMetrics(self, alarm, metrics):
        pair = (alarm['Namespace'], alarm['MetricName'])
        return pair in metrics

    def checkResourceMetricFilters(self, resource):
        logGroupArn = resource.get('CloudWatchLogsLogGroupArn')
        if not logGroupArn:
            return False

        session = local_session(self.manager.session_factory)

        groupName = re.search(':log-group:([^:]+)', logGroupArn).group(1)
        filters = self._metricFiltersForLogGroup(session, groupName)
        matchingFilters = filter(lambda mf: self.match(mf), filters)
        if not matchingFilters:
            return False
        resource['c7n:matching-metric-filters'] = matchingFilters

        # We need to filter the list of transformations to those that emit a value, and then put
        # it into a format we can easily cross compare on.
        allTransformations = map(lambda filter: filter['metricTransformations'], matchingFilters)
        transformations = sum(allTransformations, [])
        emittedMetrics = map(lambda t: (t['metricNamespace'], t['metricName']), transformations)
        if not emittedMetrics:
            return False
        resource['c7n:emitted-metric-filters'] = emittedMetrics

        consideredSet = emittedMetrics

        if self.data.get('alarm', True):
            metricAlarms = self._allAlarms(session)

            def alarmFilter(alarm):
                return self._alarmInMetrics(alarm, emittedMetrics)
            filteredAlarms = filter(alarmFilter, metricAlarms)
            if not filteredAlarms:
                return False
            consideredSet = filteredAlarms
            resource['c7n:metric-filter-alarms'] = filteredAlarms
            if self.data.get('topic-subscription'):
                alarmSNSTopics = sum(map(lambda alarm: alarm['AlarmActions'], filteredAlarms), [])
                if not alarmSNSTopics:
                    return False
                consideredSet = self._filterTopicArnsToSubscribed(session, alarmSNSTopics)
                resource['c7n:subscribed-metric-filter-alarm-topics'] = consideredSet

        return any(consideredSet)

    def process(self, resources, event=None):
        return [resource for resource in resources if self.checkResourceMetricFilters(resource)]
