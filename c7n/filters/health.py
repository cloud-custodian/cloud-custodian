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

import itertools
from c7n.utils import local_session, type_schema
from .core import Filter


class healthEventFilter(Filter):
    """Check if there are health events related to the resources"""

    schema = type_schema(
            'health-events',
            entityValues={'type': 'array', 'items': {'type': 'string'}},
            eventTypeCodes={'type': 'array', 'items': {'type': 'string'}},
            eventStatusCodes={'type': 'array', 'items': {'type': 'string'}})
    permissions = ('health:DescribeEvents', 'health:DescribeAffectedEntities',
        'health:DescribeEventDetails')

    def process(self, resources, event=None):
        results = []
        if len(resources) == 0:
            return results
        client = local_session(self.manager.session_factory).client('health')
        m = self.manager.get_model()
        resource_map = {r[m.id]: r for r in resources}
        paginator = client.get_paginator('describe_events')
        statusCodes = self.data.get('eventStatusCodes', ['open', 'upcoming'])
        f = {'services': [m.service.upper()], 'eventStatusCodes': statusCodes}
        if self.data.get('entityValues'):
            f['entityValues'] = self.data.get('entityValues')
        if self.data.get('eventTypeCodes'):
            f['eventTypeCodes'] = self.data.get('eventTypeCodes')
        events = list(itertools.chain(
            *[p['events']for p in paginator.paginate(filter=f)]))
        eventArns = list(itertools.chain(e['arn'] for e in events))
        for arn in eventArns:
            entity = client.describe_affected_entities(filter={
                'eventArns': [arn]})['entities'][0]['entityValue']
            if entity not in resource_map:
                continue
            eventDetail = client.describe_event_details(eventArns=[arn])
            resource_map[entity]['HealthEvent'] = {
                'entityValue': entity,
                'startTime': eventDetail['successfulSet'][0]
                                ['event']['startTime'],
                'eventTypeCode': eventDetail['successfulSet'][0]
                                ['event']['eventTypeCode'],
                'eventDescription': eventDetail['successfulSet'][0]
                                ['eventDescription']['latestDescription']}
            results.append(resource_map[entity])
        return results
