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

import itertools

from c7n.utils import local_session, chunks, type_schema
from .core import Filter


class HealthEventFilter(Filter):
    """Check if there are health events related to the resources



    Health events are stored as annotation on a resource.
    """

    schema = type_schema(
        'health-event',
        types={'type': 'array', 'items': {'type': 'string'}},
        statuses={'type': 'array', 'items': {
            'type': 'string',
            'enum': ['open', 'upcoming', 'closed']
        }})

    permissions = ('health:DescribeEvents', 'health:DescribeAffectedEntities',
                   'health:DescribeEventDetails')

    def process(self, resources, event=None):
        if not resources:
            return resources

        client = local_session(self.manager.session_factory).client(
            'health', region_name='us-east-1')
        f = self.get_filter_parameters()
        resource_map = {r[self.manager.get_model().id]: r for r in resources}
        found = set()
        seen = set()

        for resource_set in chunks(resource_map.keys(), 100):
            f['entityValues'] = resource_set
            events = client.describe_events(filter=f)['events']
            events = [e for e in events if e['arn'] not in seen]
            entities = self.process_event(events)

            event_map = {e['arn']: e for e in events}
            for e in entities:
                rid = e['entityValue']
                if rid not in resource_map:
                    continue
                resource_map[rid].setdefault(
                    'c7n:HealthEvent', []).append(event_map[e['eventArn']])
                found.add(rid)
            seen.update(event_map.keys())
        return [resource_map[resource_id] for resource_id in found]

    def get_filter_parameters(self):
        m = self.manager
        if m.data['resource'] == 'ebs':
            service = 'EBS'
        else:
            service = m.get_model().service.upper()
        f = {'services': [service],
             'eventStatusCodes': self.data.get(
                 'statuses', ['open', 'upcoming'])}
        if self.data.get('types'):
            f['eventTypeCodes'] = self.data.get('types')
        return f

    def process_event(self, health_events):
        entities = []
        client = local_session(self.manager.session_factory).client(
            'health', region_name='us-east-1')
        for event_set in chunks(health_events, 10):
            event_map = {e['arn']: e for e in event_set}
            for d in client.describe_event_details(
                    eventArns=event_map.keys()).get('successfulSet', ()):
                event_map[d['event']['arn']]['Description'] = d[
                    'eventDescription']['latestDescription']
            paginator = client.get_paginator('describe_affected_entities')
            entities.extend(list(itertools.chain(
                            *[p['entities']for p in paginator.paginate(
                                filter={'eventArns': event_map.keys()})])))
        return entities
