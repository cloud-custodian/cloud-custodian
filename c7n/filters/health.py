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
from c7n.utils import local_session, chunks, type_schema
from .core import Filter


class healthEventFilter(Filter):
    """Check if there are health events related to the resources"""

    schema = type_schema(
            'health-events',
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
        statusCodes = self.data.get('eventStatusCodes', ['open', 'upcoming'])
        f = {'services': [m.service.upper()], 'eventStatusCodes': statusCodes}
        if self.data.get('eventTypeCodes'):
            f['eventTypeCodes'] = self.data.get('eventTypeCodes')
        resource_map = {r[m.id]: r for r in resources}
        for resource_set in chunks(resource_map.keys(), 100):
            f['entityValues'] = resource_set
            events = client.describe_events(filter=f)['events']
            for event in events:
                arn = event['arn']
                entity = client.describe_affected_entities(filter={
                    'eventArns': [arn]})['entities'][0]['entityValue']
                if entity not in resource_map:
                    continue
                eventDetail = client.describe_event_details(eventArns=[arn])
                resource_map[entity].setdefault('HealthEvent', []).append(
                    {'entityValue': entity,
                     'startTime': eventDetail['successfulSet'][0]
                                    ['event']['startTime'],
                     'eventTypeCode': eventDetail['successfulSet'][0]
                                    ['event']['eventTypeCode'],
                     'eventDescription': eventDetail['successfulSet'][0]
                                    ['eventDescription']['latestDescription']})
                results.append(resource_map[entity])
        return results
