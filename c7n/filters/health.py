# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import itertools

from c7n.utils import local_session, chunks, type_schema
from .core import Filter
from c7n.manager import resources


class HealthEventFilter(Filter):
    """Check if there are operations health events (phd) related to the resources

    https://aws.amazon.com/premiumsupport/technology/personal-health-dashboard/

    Health events are stored as annotation on a resource.

    Custodian also supports responding to phd events via a lambda execution mode.
    """
    schema_alias = True
    schema = type_schema(
        'health-event',
        types={'type': 'array', 'items': {'type': 'string'}},
        category={'type': 'array', 'items': {
            'enum': ['issue', 'accountNotification', 'scheduledChange']}},
        statuses={'type': 'array', 'items': {
            'type': 'string',
            'enum': ['open', 'upcoming', 'closed']
        }})
    permissions = ('health:DescribeEvents', 'health:DescribeAffectedEntities',
                   'health:DescribeEventDetails')

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client(
            'health', region_name='us-east-1')
        f = self.get_filter_parameters()
        if self.manager.data['resource'] in {'app-elb'}:
            id_attr = self.manager.get_model().name
        else:
            id_attr = self.manager.get_model().id
        resource_map = {r[id_attr]: r for r in resources}
        found = set()
        seen = set()

        for resource_set in chunks(resource_map.keys(), 99):
            f['entityValues'] = resource_set
            events = client.describe_events(filter=f)['events']
            events = [e for e in events if e['arn'] not in seen]
            entities = self.process_event(client, events)

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
        phd_svc_name_map = {
            'app-elb': 'ELASTICLOADBALANCING',
            'ebs': 'EBS',
            'efs': 'ELASTICFILESYSTEM',
            'elb': 'ELASTICLOADBALANCING',
            'emr': 'ELASTICMAPREDUCE'
        }
        m = self.manager
        service = phd_svc_name_map.get(m.data['resource'], m.get_model().service.upper())
        f = {'services': [service],
             'regions': [self.manager.config.region, 'global'],
             'eventStatusCodes': self.data.get(
                 'statuses', ['open', 'upcoming'])}
        if self.data.get('types'):
            f['eventTypeCodes'] = self.data.get('types')
        return f

    def process_event(self, client, health_events):
        entities = []
        for event_set in chunks(health_events, 10):
            event_map = {e['arn']: e for e in event_set}
            event_arns = list(event_map.keys())
            for d in client.describe_event_details(
                    eventArns=event_arns).get('successfulSet', ()):
                event_map[d['event']['arn']]['Description'] = d[
                    'eventDescription']['latestDescription']
            paginator = client.get_paginator('describe_affected_entities')
            entities.extend(list(itertools.chain(
                            *[p['entities'] for p in paginator.paginate(
                                filter={'eventArns': event_arns})])))
        return entities

    @classmethod
    def register_resources(klass, registry, resource_class):
        """ meta model subscriber on resource registration.

        We watch for PHD event that provides affected entities and register
        the health-event filter to the resources.
        """
        services = {'acm-certificate', 'directconnect', 'dms-instance', 'directory', 'ec2',
                    'dynamodb-table', 'cache-cluster', 'efs', 'app-elb', 'elb', 'emr', 'rds',
                    'storage-gateway'}
        if resource_class.type in services:
            resource_class.filter_registry.register('health-event', klass)


resources.subscribe(HealthEventFilter.register_resources)
