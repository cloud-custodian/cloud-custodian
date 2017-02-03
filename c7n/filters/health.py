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

from c7n.utils import local_session, type_schema
from .core import Filter

class healthEventFilter(Filter):
    """Check if there are health events related to the resources"""

    schema = type_schema(
            'health-events',
            required=['eventTypeCodes'],
            eventTypeCodes={'type': 'array', 'items': {'type': 'string'}},
            eventStatusCodes={'type': 'array', 'items': {'type': 'string'}})

    def process(self, resources, event=None):
        results = []
        if len(resources) > 0:
            client = local_session(
                self.manager.session_factory).client('health')
            resource_map = self.get_resource_map(resources)
            statusCodes = self.data.get('eventStatusCodes',['open','upcoming'])
            eventArns = []
            paginator = client.get_paginator('describe_events')
            for p in paginator.paginate(filter={
                'eventTypeCodes': self.data.get('eventTypeCodes'),
                'eventStatusCodes': statusCodes}):
                eventArns.extend([e['arn'] for e in p['events']])
            for arn in eventArns:
                entity = client.describe_affected_entities(filter={
                    'eventArns':[arn]})['entities'][0]['entityValue']
                if entity in resource_map:
                    eventDetail = client.describe_event_details(eventArns=[arn]
                        )
                    resource_map[entity]['HealthEvent'] = {
                    'startTime':eventDetail['successfulSet'][0]['event']['startTime'],
                    'eventDescription':eventDetail['successfulSet'][0]['eventDescription']['latestDescription']}
                    results.append(resource_map[entity])
        return results

    def get_resource_map(self, resources):
        return {r['Id']: r for r in resources}