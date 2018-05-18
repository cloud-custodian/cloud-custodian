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
from __future__ import absolute_import, division, print_function, unicode_literals

import itertools

import six

from c7n.exceptions import PolicyValidationError
from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import local_session, chunks


@resources.register('health-event')
class HealthEvents(QueryResourceManager):
    """Query resource manager for AWS health events
    """

    class resource_type(object):
        service = 'health'
        type = 'event'
        enum_spec = ('describe_events', 'events', None)
        name = 'eventTypeCode'
        id = 'arn'
        filter_name = None
        filter_type = None
        dimension = None
        date = 'startTime'

    permissions = (
        'health:DescribeEvents',
        'health:DescribeEventDetails',
        'health:DescribeAffectedEntities')

    def __init__(self, ctx, data):
        super(HealthEvents, self).__init__(ctx, data)
        self.queries = QueryFilter.parse(
            self.data.get('query', [
                {'eventStatusCodes': 'open'},
                {'eventTypeCategories': ['issue', 'accountNotification']}]))

    def resource_query(self):
        qf = {}
        for q in self.queries:
            qd = q.query()
            if qd['Name'] in qf:
                for qv in qf[qd['Name']]:
                    if qv in qf[qd['Name']]:
                        continue
                    qf[qd['Name']].append(qv)
            else:
                qf[qd['Name']] = []
                for qv in qd['Values']:
                    qf[qd['Name']].append(qv)
        return qf

    def resources(self, query=None):
        q = self.resource_query()
        if q is not None:
            query = query or {}
            query['filter'] = q
        return super(HealthEvents, self).resources(query=query)

    def augment(self, resources):
        client = local_session(self.session_factory).client('health')
        for resource_set in chunks(resources, 10):
            event_map = {r['arn']: r for r in resource_set}
            event_details = client.describe_event_details(
                eventArns=list(event_map.keys()))['successfulSet']
            for d in event_details:
                event_map[d['event']['arn']][
                    'Description'] = d['eventDescription']['latestDescription']

            event_arns = [r['arn'] for r in resource_set
                          if r['eventTypeCategory'] != 'accountNotification']

            if not event_arns:
                continue
            paginator = client.get_paginator('describe_affected_entities')
            entities = list(itertools.chain(
                *[p['entities']for p in paginator.paginate(
                    filter={'eventArns': event_arns})]))

            for e in entities:
                event_map[e.pop('eventArn')].setdefault(
                    'AffectedEntities', []).append(e)

        return resources


HEALTH_VALID_FILTERS = {
    'availability-zone': str,
    'eventTypeCategories': {'issue', 'accountNotification', 'scheduledChange'},
    'regions': str,
    'services': str,
    'eventStatusCodes': {'open', 'closed', 'upcoming'},
    'eventTypeCodes': str
}


class QueryFilter(object):

    @classmethod
    def parse(cls, data):
        results = []
        for d in data:
            if not isinstance(d, dict):
                raise PolicyValidationError(
                    "Health Query Filter Invalid structure %s" % d)
            results.append(cls(d).validate())
        return results

    def __init__(self, data):
        self.data = data
        self.key = None
        self.value = None

    def validate(self):
        if not len(list(self.data.keys())) == 1:
            raise ValueError(
                "Health Query Filter Invalid %s" % self.data)
        self.key = list(self.data.keys())[0]
        self.value = list(self.data.values())[0]

        if self.key not in HEALTH_VALID_FILTERS:
            raise PolicyValidationError(
                "Health Query Filter invalid filter name %s" % (self.data))

        if self.value is None:
            raise PolicyValidationError(
                "Health Query Filters must have a value, use tag-key"
                " w/ tag name as value for tag present checks"
                " %s" % self.data)
        return self

    def query(self):
        value = self.value
        if isinstance(self.value, six.string_types):
            value = [self.value]
        return {'Name': self.key, 'Values': value}
