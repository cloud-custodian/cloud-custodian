# Copyright 2016-2017 Capital One Services, LLC
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
import fnmatch
import json
import itertools
import os

from botocore.paginate import Paginator

from c7n.query import QueryResourceManager, ChildResourceManager
from c7n.manager import resources
from c7n.utils import chunks, get_retry, generate_arn, local_session, type_schema
from c7n.actions import BaseAction
from c7n.filters import Filter

from c7n.resources.shield import IsShieldProtected, SetShieldProtection
from c7n.tags import RemoveTag, Tag


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

    def get_arn(self, r):
        return self.generate_arn(r[self.get_model().id].split("/")[-1])

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

        for resource_batch in chunks(list(resource_map.keys()), 10):
            results = retry(
                client.list_tags_for_resources,
                ResourceType=model.type,
                ResourceIds=resource_batch)
            for resource_tag_set in results['ResourceTagSets']:
                if ('ResourceId' in resource_tag_set and
                        resource_tag_set['ResourceId'] in resource_map):
                    resource_map[resource_tag_set['ResourceId']]['Tags'] = resource_tag_set['Tags']

    with executor_factory(max_workers=2) as w:
        return list(w.map(process_tags, chunks(resources, 20)))


@resources.register('hostedzone')
class HostedZone(Route53Base, QueryResourceManager):

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
        universal_taggable = True

    def get_arns(self, resource_set):
        arns = []
        for r in resource_set:
            _id = r[self.get_model().id].split("/")[-1]
            arns.append(self.generate_arn(_id))
        return arns


HostedZone.filter_registry.register('shield-enabled', IsShieldProtected)
HostedZone.action_registry.register('set-shield', SetShieldProtection)


@resources.register('healthcheck')
class HealthCheck(Route53Base, QueryResourceManager):

    class resource_type(object):
        service = 'route53'
        type = 'healthcheck'
        enum_spec = ('list_health_checks', 'HealthChecks', None)
        name = id = 'Id'
        filter_name = None
        date = None
        dimension = None
        universal_taggable = True


@resources.register('rrset')
class ResourceRecordSet(ChildResourceManager):

    class resource_type(object):
        service = 'route53'
        type = 'rrset'
        parent_spec = ('hostedzone', 'HostedZoneId', None)
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

    permissions = ('route53domains:ListTagsForDomain',)

    def augment(self, domains):
        client = local_session(self.session_factory).client('route53domains')

        def _list_tags(d):
            tags = client.list_tags_for_domain(
                DomainName=d['DomainName'])['TagList']
            d['Tags'] = tags
            return d

        with self.executor_factory(max_workers=1) as w:
            return list(filter(None, w.map(_list_tags, domains)))


@Route53Domain.action_registry.register('tag')
class Route53DomainAddTag(Tag):
    """Adds tags to a route53 domain

    :example:

    .. code-block: yaml

        policies:
          - name: route53-tag
            resource: r53domain
            filters:
              - "tag:DesiredTag": absent
            actions:
              - type: tag
                key: DesiredTag
                value: DesiredValue
    """
    permissions = ('route53domains:UpdateTagsForDomain',)

    def process_resource_set(self, domains, tags):
        client = local_session(
            self.manager.session_factory).client('route53domains')

        for d in domains:
            client.update_tags_for_domain(
                DomainName=d[self.id_key],
                TagsToUpdate=tags)


@Route53Domain.action_registry.register('remove-tag')
class Route53DomainRemoveTag(RemoveTag):
    """Remove tags from a route53 domain

    :example:

    .. code-block: yaml

        policies:
          - name: route53-expired-tag
            resource: r53domain
            filters:
              - "tag:ExpiredTag": present
            actions:
              - type: remove-tag
                tags: ['ExpiredTag']
    """
    permissions = ('route53domains:DeleteTagsForDomain',)

    def process_resource_set(self, domains, keys):
        client = local_session(
            self.manager.session_factory).client('route53domains')

        for d in domains:
            client.delete_tags_for_domain(
                DomainName=d[self.id_key],
                TagsToDelete=keys)


@HostedZone.action_registry.register('set-query-logging')
class SetQueryLogging(BaseAction):
    """Enables query logging on a hosted zone.

    **Note you must** create a resource policy in cloud watch logs to
    allow route53 to push logs to a log group. See
    https://amzn.to/2wAhBbs for details. One resource policy can cover
    all log-groups.

    Its recommended to use a separate custodian policy on the log
    groups to set the log retention period for the zone logs.

    :example:

    .. code-block: yaml

        policies:
          - name: enablednsquerylogging
            resource: hostedzone
            region: us-east-1
            filters:
              - type: query-logging-enabled
                state: false
            actions:
              - type: set-query-logging
                state: true

    """

    permissions = (
        'route53:GetQueryLoggingConfig',
        'route53:CreateQueryLoggingConfig',
        'route53:DeleteQueryLoggingConfig',
        'logs:DescribeLogGroups',
        'logs:CreateLogGroups',
        'logs:GetResourcePolicy',
        'logs:PutResourcePolicy')

    schema = type_schema(
        'set-query-logging', **{
            'log-group-prefix': {'type': 'string', 'default': '/aws/route53'},
            'log-group': {'type': 'string', 'default': 'auto'},
            'state': {'type': 'boolean'}})

    statement = {
        "Sid": "Route53LogsToCloudWatchLogs",
        "Effect": "Allow",
        "Principal": {"Service": ["route53.amazonaws.com"]},
        "Action": "logs:PutLogEvents",
        "Resource": None}

    def validate(self):
        if not self.data.get('state', True):
            # By forcing use of a filter we ensure both getting to right set of
            # resources as well avoiding an extra api call here, as we'll reuse
            # the annotation from the filter for logging config.
            if not [f for f in self.manager.filters if isinstance(
                    f, IsQueryLoggingEnabled)]:
                raise ValueError(
                    "set-query-logging when deleting requires "
                    "use of query-logging-enabled filter in policy")
        return self

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('route53')
        state = self.data.get('state', True)

        zone_log_names = {z['Id']: self.get_zone_log_name(z) for z in resources}
        if state:
            self.ensure_log_groups(set(zone_log_names.values()))

        for r in resources:
            if not state:
                client.delete_query_logging_config(Id=r['c7n:log-config']['Id'])
                continue
            log_arn = "arn:aws:logs:us-east-1:{}:log-group:{}".format(
                self.manager.account_id, zone_log_names[r['Id']])
            client.create_query_logging_config(
                HostedZoneId=r['Id'],
                CloudWatchLogsLogGroupArn=log_arn)

    def get_zone_log_name(self, zone):
        if self.data.get('log-group', 'auto') == 'auto':
            log_group_name = "%s/%s" % (
                self.data.get('log-group-prefix', '/aws/route53').rstrip('/'),
                zone['Name'][:-1])
        else:
            log_group_name = self.data['log-group']
        return log_group_name

    def ensure_log_groups(self, group_names):
        log_manager = self.manager.get_resource_manager('log-group')

        if len(group_names) == 1:
            groups = []
            if log_manager.get_resources(list(group_names), augment=False):
                return
        else:
            common_prefix = os.path.commonprefix(group_names)
            if common_prefix not in ('', '/'):
                groups = log_manager.get_resources(
                    [common_prefix], augment=False)
            else:
                groups = list(itertools.chain(*[
                    log_manager.get_resources([g]) for g in group_names]))

        missing = group_names.difference({g['logGroupName'] for g in groups})
        if not missing:
            return

        # Logs groups must be created in us-east-1 for route53.
        client = local_session(
            self.manager.session_factory).client('logs', region_name='us-east-1')

        for g in missing:
            client.create_log_group(logGroupName=g)

        #self.ensure_route53_permissions(client, group_names)

    def ensure_route53_permissions(self, client, group_names):
        if self.check_route53_permissions(client, group_names):
            return
        if self.data.get('log-group') != 'auto':
            resource = "arn:aws:logs:us-east-1:{}:log-group:{}".format(
                self.manager.account_id, self.data['log-group'])
        else:
            resource = "arn:aws:logs:us-east-1:{}:log-group:{}/*".format(
                self.manager.account_id,
                self.data.get('log-group-prefix', '/aws/route53').rstrip('/'))
        statement = dict(self.statement)
        statement['Resource'] = resource
        client.put_resource_policy(
            policyName='Route53LogWrites',
            policyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [self.statement]
            })
        )

    def check_route53_permissions(self, client, group_names):
        group_names = set(group_names)
        for p in client.describe_resource_policies().get('resourcePolicies', []):
            for s in json.loads(p['policyDocument']).get('Statement', []):
                if (s['Effect'] == 'Allow' and
                        s['Principal'].get('Service', ['']) == "route53.amazonaws.com"):
                    group_names.difference_update(
                        fnmatch.filter(group_names, s['Resource']))
                    if not group_names:
                        return True
        return not bool(group_names)


def get_logging_config_paginator(client):
    return Paginator(
        client.list_query_logging_configs,
        {'input_token': 'NextToken', 'output_token': 'NextToken',
         'result_key': 'QueryLoggingConfigs'},
        client.meta.service_model.operation_model('ListQueryLoggingConfigs'))


@HostedZone.filter_registry.register('query-logging-enabled')
class IsQueryLoggingEnabled(Filter):

    permissions = ('route53:GetQueryLoggingConfig', 'route53:GetHostedZone')
    schema = type_schema('query-logging-enabled', state={'type': 'boolean'})

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('route53')
        state = self.data.get('state', False)
        results = []

        enabled_zones = {
            c['HostedZoneId']: c for c in
            get_logging_config_paginator(
                client).paginate().build_full_result().get(
                    'QueryLoggingConfigs', ())}
        for r in resources:
            zid = r['Id'].split('/', 2)[-1]
            # query logging is only supported for Public Hosted Zones.
            if r['Config']['PrivateZone'] is True:
                continue
            logging = zid in enabled_zones
            if logging and state:
                r['c7n:log-config'] = enabled_zones[zid]
                results.append(r)
            elif not logging and not state:
                results.append(r)
        return results