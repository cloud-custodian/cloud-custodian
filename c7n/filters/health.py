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
            'enum': ['open', 'upcoming']
        }})

    permissions = ('health:DescribeEvents', 'health:DescribeAffectedEntities',
                   'health:DescribeEventDetails')

    def process(self, resources, event=None):
        if not resources:
            return resources

        client = local_session(self.manager.session_factory).client('health')
        m = self.manager.get_model()

        f = {'services': [m.service.upper()],
             'eventStatusCodes': self.data.get(
                 'statuses', ['open', 'upcoming'])}

        if self.data.get('eventTypeCodes'):
            f['eventTypeCodes'] = self.data.get('types')

        resource_map = {r[m.id]: r for r in resources}
        found = set()
        seen = set()

        for resource_set in chunks(resource_map.keys(), 100):
            f['entityValues'] = resource_set
            events = client.describe_events(filter=f)['events']
            events = [e for e in events if e['arn'] not in seen]

            for event_set in chunks(events, 10):
                event_map = {e['arn']: e for e in event_set}
                for d in client.describe_event_details(
                        eventArns=event_map.keys()).get('successfulSet', ()):
                    event_map[d['event']['arn']]['Description'] = d[
                        'eventDescription']['latestDescription']
                entities = client.describe_affected_entities(
                    filter={'eventArns': event_map.keys()})['entities']

                for e in entities:
                    rid = e['entityValue']
                    if rid not in resource_map:
                        continue
                    resource_map[rid].setdefault(
                        'c7n:HealthEvent', []).append(event_map[e['eventArn']])
                    found.add(rid)
                seen.update(event_map.keys())
        return [resource_map[rid] for rid in found]
