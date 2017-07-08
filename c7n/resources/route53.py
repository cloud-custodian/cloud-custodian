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

import functools

from c7n.actions import ActionRegistry, AutoTagUser
from c7n.filters import FilterRegistry
from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.tags import (
    TagActionFilter, UniversalTag, UniversalUntag, UniversalTagDelayedAction)
from c7n.utils import chunks, get_retry, generate_arn, local_session


class Route53Base(object):

    permissions = ('route53:ListTagsForResources',)
    retry = staticmethod(get_retry(('Throttled',)))

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                self.get_model().service,
                resource_type=self.get_model().type)
        return self._generate_arn

    def augment(self, resources):
        _describe_route53_tags(
            self.get_model(), resources, self.session_factory,
            self.executor_factory, self.retry)
        return resources


def _describe_route53_tags(
        model, resources, session_factory, executor_factory, retry):

    def process_tags(resources):
        client = local_session(session_factory).client('route53')
        resource_map = {}
        for r in resources:
            k = r[model.id]
            if "hostedzone" in k:
                k = k.split("/")[-1]
            resource_map[k] = r

        results = retry(
            client.list_tags_for_resources,
            ResourceType=model.type,
            ResourceIds=resource_map.keys())

        for resource_tag_set in results['ResourceTagSets']:
            if ('ResourceId' in resource_tag_set and
                    resource_tag_set['ResourceId'] in resource_map):
                resource_map[resource_tag_set['ResourceId']]['Tags'] = resource_tag_set['Tags']

    with executor_factory(max_workers=2) as w:
        return list(w.map(process_tags, chunks(resources, 20)))


@resources.register('hostedzone')
class HostedZone(Route53Base, QueryResourceManager):

    filter_registry = FilterRegistry('hostedzone.filters')
    filter_registry.register('marked-for-op', TagActionFilter)

    action_registry = ActionRegistry('hostedzone.actions')
    action_registry.register('auto-tag-user', AutoTagUser)
    action_registry.register('mark', UniversalTag)
    action_registry.register('tag', UniversalTag)
    action_registry.register('mark-for-op', UniversalTagDelayedAction)
    action_registry.register('remove-tag', UniversalUntag)
    action_registry.register('unmark', UniversalUntag)
    action_registry.register('untag', UniversalUntag)

    class resource_type(object):
        service = 'route53'
        type = 'hostedzone'
        enum_spec = ('list_hosted_zones', 'HostedZones', None)
        # detail_spec = ('get_hosted_zone', 'Id', 'Id', None)
        id = 'Id'
        filter_name = None
        name = 'Name'
        date = None
        dimension = None

    def get_arns(self, resource_set):
        arns = []
        for r in resource_set:
            _id = r[self.get_model().id].split("/")[-1]
            arns.append(self.generate_arn(_id))
        return arns


@resources.register('healthcheck')
class HealthCheck(Route53Base, QueryResourceManager):

    filter_registry = FilterRegistry('healthcheck.filters')
    filter_registry.register('marked-for-op', TagActionFilter)

    action_registry = ActionRegistry('healthcheck.actions')
    action_registry.register('auto-tag-user', AutoTagUser)
    action_registry.register('mark', UniversalTag)
    action_registry.register('tag', UniversalTag)
    action_registry.register('mark-for-op', UniversalTagDelayedAction)
    action_registry.register('remove-tag', UniversalUntag)
    action_registry.register('unmark', UniversalUntag)
    action_registry.register('untag', UniversalUntag)

    class resource_type(object):
        service = 'route53'
        type = 'healthcheck'
        enum_spec = ('list_health_checks', 'HealthChecks', None)
        name = id = 'Id'
        filter_name = None
        date = None
        dimension = None


@resources.register('rrset')
class ResourceRecordSet(QueryResourceManager):

    class resource_type(object):
        service = 'route53'
        type = 'rrset'
        enum_spec = ('list_resource_record_sets', 'ResourceRecordSets', None)
        name = id = 'Name'
        filter_name = None
        date = None
        dimension = None


@resources.register('r53domain')
class Route53Domain(QueryResourceManager):

    class resource_type(object):
        service = 'route53domains'
        type = 'r53domain'
        enum_spec = ('list_domains', 'Domains', None)
        name = id = 'DomainName'
        filter_name = None
        date = None
        dimension = None
