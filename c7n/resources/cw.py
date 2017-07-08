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
from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime, timedelta

from c7n.actions import BaseAction
from c7n.filters import Filter
from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import type_schema, local_session, chunks, get_retry


@resources.register('alarm')
class Alarm(QueryResourceManager):

    class resource_type(object):
        service = 'cloudwatch'
        type = 'alarm'
        enum_spec = ('describe_alarms', 'MetricAlarms', None)
        id = 'AlarmArn'
        filter_name = 'AlarmNames'
        filter_type = 'list'
        name = 'AlarmName'
        date = 'AlarmConfigurationUpdatedTimestamp'
        dimension = None

    retry = staticmethod(get_retry(('Throttled',)))


@Alarm.action_registry.register('delete')
class AlarmDelete(BaseAction):
    """Delete a cloudwatch alarm.

    :example:

        .. code-block: yaml

            policies:
              - name: cloudwatch-delete-stale-alarms
                resource: alarm
                filters:
                  - type: value
                    value_type: age
                    key: StateUpdatedTimestamp
                    value: 30
                    op: ge
                  - StateValue: INSUFFICIENT_DATA
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('cloudwatch:DeleteAlarms',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('cloudwatch')

        for resource_set in chunks(resources, size=100):
            self.manager.retry(
                client.delete_alarms,
                AlarmNames=[r['AlarmName'] for r in resource_set])


@resources.register('event-rule')
class EventRule(QueryResourceManager):

    class resource_type(object):
        service = 'events'
        type = 'event-rule'
        enum_spec = ('list_rules', 'Rules', None)
        name = "Name"
        id = "Name"
        filter_name = "NamePrefix"
        filer_type = "scalar"
        dimension = "RuleName"


@resources.register('log-group')
class LogGroup(QueryResourceManager):

    class resource_type(object):
        service = 'logs'
        type = 'log-group'
        enum_spec = ('describe_log_groups', 'logGroups', None)
        name = 'logGroupName'
        id = 'arn'
        filter_name = 'logGroupNamePrefix'
        filter_type = 'scalar'
        dimension = 'LogGroupName'
        date = 'creationTime'


@LogGroup.action_registry.register('retention')
class Retention(BaseAction):
    """Action to set the retention period (in days) for CloudWatch log groups

    :example:

        .. code-block: yaml

            policies:
              - name: cloudwatch-set-log-group-retention
                resource: log-group
                actions:
                  - type: retention
                    days: 200
    """

    schema = type_schema('retention', days={'type': 'integer'})
    permissions = ('logs:PutRetentionPolicy',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('logs')
        days = self.data['days']
        for r in resources:
            client.put_retention_policy(
                logGroupName=r['logGroupName'],
                retentionInDays=days)


@LogGroup.action_registry.register('delete')
class Delete(BaseAction):
    """

    :example:

        .. code-block: yaml

            policies:
              - name: cloudwatch-delete-stale-log-group
                resource: log-group
                filters:
                  - type: last-write
                    days: 182.5
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('logs:DeleteLogGroup',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('logs')
        for r in resources:
            client.delete_log_group(logGroupName=r['logGroupName'])


@LogGroup.filter_registry.register('last-write')
class LastWriteDays(Filter):
    """Filters CloudWatch log groups by last write

    :example:

        .. code-block: yaml

            policies:
              - name: cloudwatch-stale-groups
                resource: log-group
                filters:
                  - type: last-write
                    days: 60
    """

    schema = type_schema(
        'last-write', days={'type': 'number'})
    permissions = ('logs:DescribeLogStreams',)

    def process(self, resources, event=None):
        self.date_threshold = datetime.utcnow() - timedelta(
            days=self.data['days'])
        return super(LastWriteDays, self).process(resources)

    def __call__(self, group):
        self.log.debug("Processing group %s", group['logGroupName'])
        logs = local_session(self.manager.session_factory).client('logs')
        streams = logs.describe_log_streams(
            logGroupName=group['logGroupName'],
            orderBy='LastEventTime',
            descending=True,
            limit=3).get('logStreams')
        group['streams'] = streams
        if not streams:
            last_timestamp = group['creationTime']
        elif streams[0]['storedBytes'] == 0:
            last_timestamp = streams[0]['creationTime']
        else:
            last_timestamp = streams[0]['lastIngestionTime']

        last_write = datetime.fromtimestamp(last_timestamp / 1000.0)
        group['lastWrite'] = last_write
        return self.date_threshold > last_write
