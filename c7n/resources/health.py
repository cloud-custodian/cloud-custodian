# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import itertools

from c7n.query import QueryResourceManager, TypeInfo
from c7n.manager import resources
from c7n.utils import local_session, chunks, QueryParser


@resources.register('health-event')
class HealthEvents(QueryResourceManager):
    """Query resource manager for AWS health events
    """

    class resource_type(TypeInfo):
        service = 'health'
        arn = 'arn'
        arn_type = 'event'
        enum_spec = ('describe_events', 'events', None)
        name = 'eventTypeCode'
        global_resource = True
        id = 'arn'
        date = 'startTime'

    permissions = (
        'health:DescribeEvents',
        'health:DescribeEventDetails',
        'health:DescribeAffectedEntities')

    def __init__(self, ctx, data):
        super(HealthEvents, self).__init__(ctx, data)
        self.queries = HealthQueryParser.parse(
            self.data.get('query', [
                {'eventStatusCodes': 'open'},
                {'eventTypeCategories': ['issue', 'accountNotification']}]))

    def resource_query(self):
        qf = {}
        for q in self.queries:
            key = list(q.keys())[0]
            values = list(q.values())[0]
            qf[key] = values
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


class HealthQueryParser(QueryParser):
    QuerySchema = {
        'availabilityZones': str,
        'eventTypeCategories': ('issue', 'accountNotification', 'scheduledChange', 'investigation'),
        'regions': str,
        'services': str,
        'eventStatusCodes': ('open', 'closed', 'upcoming'),
        'eventTypeCodes': str,
        'maxResults': int,
    }
    single_value_fields = ('maxResults')

    type_name = 'Health Event'
