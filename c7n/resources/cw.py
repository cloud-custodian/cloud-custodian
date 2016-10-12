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
from datetime import datetime, timedelta

from c7n.actions import BaseAction
from c7n.filters import Filter
from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import type_schema, local_session


@resources.register('alarm')
class Alarm(QueryResourceManager):

    resource_type = 'aws.cloudwatch.alarm'


@resources.register('log-group')
class LogGroup(QueryResourceManager):

    class Meta(object):

        service = 'logs'
        type = 'log-group'
        enum_spec = ('describe_log_groups', 'logGroups', None)

        name = 'logGroupName'
        id = 'arn'
        filter_name = 'logGroupNamePrefix'
        filter_type = 'scalar'
        dimension = 'LogGroupName'
        date = 'creationTime'

    resource_type = Meta


@LogGroup.action_registry.register('retention')
class Retention(BaseAction):

    schema = type_schema(
        'retention', days={'type': 'integer'})

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('logs')
        days = self.data['days']
        for r in resources:
            client.put_retention_policy(
                logGroupName=r['logGroupName'],
                retentionInDays=days)


@LogGroup.action_registry.register('delete')
class Delete(BaseAction):

    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('logs')
        for r in resources:
            client.delete_log_group(logGroupName=r['logGroupName'])


@LogGroup.filter_registry.register('last-write')
class LastWriteDays(Filter):

    schema = type_schema(
        'last-write', days={'type': 'number'})

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
            limit=3).get('logStreams')
        group['streams'] = streams
        if not streams:
            last_timestamp = group['creationTime']
        elif streams[0]['storedBytes'] == 0:
            last_timestamp = streams[0]['creationTime']
        else:
            last_timestamp = streams[0]['lastIngestionTime']

        last_write = datetime.fromtimestamp(last_timestamp/1000.0)
        group['lastWrite'] = last_write
        return self.date_threshold > last_write
