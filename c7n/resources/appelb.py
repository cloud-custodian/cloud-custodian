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
"""
Application Load Balancers
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import itertools
import logging

from collections import defaultdict
from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import (
    Filter, FilterRegistry, FilterValidationError, DefaultVpcBase,
    MetricsFilter, ValueFilter)
import c7n.filters.vpc as net_filters
from c7n import tags
from c7n.manager import resources

from c7n.query import QueryResourceManager, DescribeSource, ConfigSource
from c7n.utils import (
    local_session, chunks, type_schema, get_retry, set_annotation)

from c7n.resources.shield import IsShieldProtected, SetShieldProtection

log = logging.getLogger('custodian.app-elb')

filters = FilterRegistry('app-elb.filters')
actions = ActionRegistry('app-elb.actions')

filters.register('tag-count', tags.TagCountFilter)
filters.register('marked-for-op', tags.TagActionFilter)


@resources.register('app-elb')
class AppELB(QueryResourceManager):
    """Resource manager for v2 ELBs (AKA ALBs).
    """

    class resource_type(object):

        service = 'elbv2'
        type = 'loadbalancer/app'

        enum_spec = ('describe_load_balancers', 'LoadBalancers', None)
        name = 'LoadBalancerName'
        id = 'LoadBalancerArn'
        filter_name = None
        filter_type = None
        dimension = "LoadBalancer"
        date = 'CreatedTime'
        config_type = 'AWS::ElasticLoadBalancingV2::LoadBalancer'

    filter_registry = filters
    action_registry = actions
    retry = staticmethod(get_retry(('Throttling',)))

    @classmethod
    def get_permissions(cls):
        # override as the service is not the iam prefix
        return ("elasticloadbalancing:DescribeLoadBalancers",
                "elasticloadbalancing:DescribeLoadBalancerAttributes",
                "elasticloadbalancing:DescribeTags")

    def get_arn(self, r):
        return r[self.resource_type.id]

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeAppElb(self)
        elif source_type == 'config':
            return ConfigAppElb(self)
        raise ValueError("Unsupported source: %s for %s" % (
            source_type, self.resource_type.config_type))


class DescribeAppElb(DescribeSource):

    def augment(self, albs):
        _describe_appelb_tags(
            albs,
            self.manager.session_factory,
            self.manager.executor_factory,
            self.manager.retry)

        return albs


class ConfigAppElb(ConfigSource):

    def load_resource(self, item):
        resource = super(ConfigAppElb, self).load_resource(item)
        resource['Tags'] = [{u'Key': t['key'], u'Value': t['value']}
          for t in json.loads(item['supplementaryConfiguration']['Tags'])]
        return resource


def _describe_appelb_tags(albs, session_factory, executor_factory, retry):
    def _process_tags(alb_set):
        client = local_session(session_factory).client('elbv2')
        alb_map = {alb['LoadBalancerArn']: alb for alb in alb_set}

        results = retry(client.describe_tags, ResourceArns=list(alb_map.keys()))
        for tag_desc in results['TagDescriptions']:
            if ('ResourceArn' in tag_desc and
                    tag_desc['ResourceArn'] in alb_map):
                alb_map[tag_desc['ResourceArn']]['Tags'] = tag_desc['Tags']

    with executor_factory(max_workers=2) as w:
        list(w.map(_process_tags, chunks(albs, 20)))


def _add_appelb_tags(albs, session_factory, ts):
    client = local_session(session_factory).client('elbv2')
    client.add_tags(
        ResourceArns=[alb['LoadBalancerArn'] for alb in albs],
        Tags=ts)


def _remove_appelb_tags(albs, session_factory, tag_keys):
    client = local_session(session_factory).client('elbv2')
    client.remove_tags(
        ResourceArns=[alb['LoadBalancerArn'] for alb in albs],
        TagKeys=tag_keys)


filters.register('shield-enabled', IsShieldProtected)
actions.register('set-shield', SetShieldProtection)


@filters.register('metrics')
class AppElbMetrics(MetricsFilter):
    """Filter app load balancer by metric values.

    See available metrics here: https://goo.gl/TLQ9Fr
    Custodian defaults to specifying dimensions for the app elb only.
    Target Group dimension not supported atm.
    """

    def get_dimensions(self, resource):
        return [{
            'Name': self.model.dimension,
            'Value': 'app/%s/%s' % (
                resource[self.model.name],
                resource[self.model.id].rsplit('/')[-1])}]


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[]"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "AvailabilityZones[].SubnetId"


filters.register('network-location', net_filters.NetworkLocation)


@AppELB.filter_registry.register('waf-enabled')
class WafEnabled(Filter):

    schema = type_schema(
        'waf-enabled', **{
            'web-acl': {'type': 'string'},
            'state': {'type': 'boolean'}})

    permissions = ('waf-regional:ListResourcesForWebACL', 'waf-regional:ListWebACLs')

    # TODO verify name uniqueness within region/account
    # TODO consider associated resource fetch in augment
    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client(
            'waf-regional')

        target_acl = self.data.get('web-acl')
        state = self.data.get('state', False)

        name_id_map = {}
        resource_map = {}

        wafs = self.manager.get_resource_manager('waf-regional').resources()

        for w in wafs:
            if 'c7n:AssociatedResources' not in w:
                arns = client.list_resources_for_web_acl(
                    WebACLId=w['WebACLId']).get('ResourceArns', [])
                w['c7n:AssociatedResources'] = arns
            name_id_map[w['Name']] = w['WebACLId']
            for r in w['c7n:AssociatedResources']:
                resource_map[r] = w['WebACLId']

        target_acl_id = name_id_map.get(target_acl, target_acl)

        # generally frown on runtime validation errors, but also frown on
        # api calls during validation.
        if target_acl_id not in name_id_map.values():
            raise ValueError("Invalid target acl:%s, acl not found" % target_acl)

        arn_key = self.manager.resource_type.id

        state_map = {}
        for r in resources:
            arn = r[arn_key]
            if arn in resource_map:
                r['c7n_webacl'] = resource_map[arn]
                if not target_acl:
                    state_map[arn] = True
                    continue
                r_acl = resource_map[arn]
                if r_acl == target_acl_id:
                    state_map[arn] = True
                    continue
                state_map[arn] = False
            else:
                state_map[arn] = False
        return [r for r in resources if state_map[r[arn_key]] == state]


@AppELB.action_registry.register('set-waf')
class SetWaf(BaseAction):
    """Enable/Disable waf protection on applicable resource.

    """
    permissions = ('waf-regional:AssociateWebACL', 'waf-regional:ListWebACLs')

    schema = type_schema(
        'set-waf', required=['web-acl'], **{
            'web-acl': {'type': 'string'},
            # 'force': {'type': 'boolean'},
            'state': {'type': 'boolean'}})

    def validate(self):
        found = False
        for f in self.manager.filters:
            if isinstance(f, WafEnabled):
                found = True
                break
        if not found:
            # try to ensure idempotent usage
            raise FilterValidationError(
                "set-waf should be used in conjunction with waf-enabled filter")
        return self

    def process(self, resources):
        wafs = self.manager.get_resource_manager('waf-regional').resources()
        name_id_map = {w['Name']: w['WebACLId'] for w in wafs}
        target_acl = self.data.get('web-acl')
        target_acl_id = name_id_map.get(target_acl, target_acl)
        state = self.data.get('state', True)

        if state and target_acl_id not in name_id_map.values():
            raise ValueError("invalid web acl: %s" % (target_acl_id))

        client = local_session(
            self.manager.session_factory).client('waf-regional')

        arn_key = self.manager.resource_type.id

        # TODO implement force to reassociate.
        # TODO investigate limits on waf association.
        for r in resources:
            if state:
                client.associate_web_acl(
                    WebACLId=target_acl_id, ResourceArn=r[arn_key])
            else:
                client.disassociate_web_acl(
                    WebACLId=target_acl_id, ResourceArn=r[arn_key])


@actions.register('set-s3-logging')
class SetS3Logging(BaseAction):
    """Action to enable/disable S3 logging for an application loadbalancer.

    :example:

    .. code-block:: yaml

            policies:
              - name: elbv2-test
                resource: app-elb
                filters:
                  - type: value
                    key: Attributes."access_logs.s3.enabled"
                    value: False
                actions:
                  - type: enable-s3-logging
                    bucket: elbv2logtest
                    prefix: dahlogs
    """
    schema = type_schema(
        'set-s3-logging',
        state={'enum': ['enabled', 'disabled']},
        bucket={'type': 'string'},
        prefix={'type': 'string'},
        required=('state',))

    permissions = ("elasticloadbalancing:ModifyLoadBalancerAttributes",)

    def validate(self):
        if self.data.get('state') == 'enabled':
            if 'bucket' not in self.data or 'prefix' not in self.data:
                raise FilterValidationError((
                    "alb logging enablement requires `bucket` "
                    "and `prefix` specification"))
        return self

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('elbv2')
        for elb in resources:
            elb_arn = elb['LoadBalancerArn']
            attributes = [{
                'Key': 'access_logs.s3.enabled',
                'Value': (
                    self.data.get('state') == 'enabled' and 'true' or 'value')}]

            if self.data.get('state') == 'enabled':
                attributes.append({
                    'Key': 'access_logs.s3.bucket',
                    'Value': self.data['bucket']})

                prefix_template = self.data['prefix']
                info = {t['Key']: t['Value'] for t in elb.get('Tags', ())}
                info['DNSName'] = elb.get('DNSName', '')
                info['AccountId'] = elb['LoadBalancerArn'].split(':')[4]
                info['LoadBalancerName'] = elb['LoadBalancerName']

                attributes.append({
                    'Key': 'access_logs.s3.prefix',
                    'Value': prefix_template.format(**info)})

            self.manager.retry(
                client.modify_load_balancer_attributes,
                LoadBalancerArn=elb_arn, Attributes=attributes)


@actions.register('mark-for-op')
class AppELBMarkForOpAction(tags.TagDelayedAction):
    """Action to create a delayed action on an ELB to start at a later date

    :example:

    .. code-block:: yaml

            policies:
              - name: appelb-failed-mark-for-op
                resource: app-elb
                filters:
                  - "tag:custodian_elb_cleanup": absent
                  - State: failed
                actions:
                  - type: mark-for-op
                    tag: custodian_elb_cleanup
                    msg: "AppElb failed: {op}@{action_date}"
                    op: delete
                    days: 1
    """

    batch_size = 1
    permissions = ("elasticloadbalancing:AddTags",)

    def process_resource_set(self, resource_set, ts):
        _add_appelb_tags(
            resource_set,
            self.manager.session_factory,
            ts)


@actions.register('tag')
class AppELBTagAction(tags.Tag):
    """Action to create tag/tags on an ELB

    :example:

    .. code-block:: yaml

            policies:
              - name: appelb-create-required-tag
                resource: app-elb
                filters:
                  - "tag:RequiredTag": absent
                actions:
                  - type: tag
                    key: RequiredTag
                    value: RequiredValue
    """

    batch_size = 1
    permissions = ("elasticloadbalancing:AddTags",)

    def process_resource_set(self, resource_set, ts):
        _add_appelb_tags(
            resource_set,
            self.manager.session_factory,
            ts)


@actions.register('remove-tag')
class AppELBRemoveTagAction(tags.RemoveTag):
    """Action to remove tag/tags from an ELB

    :example:

    .. code-block:: yaml

            policies:
              - name: appelb-delete-expired-tag
                resource: app-elb
                filters:
                  - "tag:ExpiredTag": present
                actions:
                  - type: remove-tag
                    tags: ["ExpiredTag"]
    """

    batch_size = 1
    permissions = ("elasticloadbalancing:RemoveTags",)

    def process_resource_set(self, resource_set, tag_keys):
        _remove_appelb_tags(
            resource_set,
            self.manager.session_factory,
            tag_keys)


@actions.register('delete')
class AppELBDeleteAction(BaseAction):
    """Action to delete an ELB

    To avoid unwanted deletions of ELB, it is recommended to apply a filter
    to the rule

    :example:

    .. code-block:: yaml

            policies:
              - name: appelb-delete-failed-elb
                resource: app-elb
                filters:
                  - State: failed
                actions:
                  - delete
    """

    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = (
        "elasticloadbalancing:DeleteLoadBalancer",
        "elasticloadbalancing:ModifyLoadBalancerAttributes",)

    def process(self, load_balancers):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_alb, load_balancers))

    def process_alb(self, alb):
        client = local_session(self.manager.session_factory).client('elbv2')
        try:
            if self.data.get('force'):
                client.modify_load_balancer_attributes(
                    LoadBalancerArn=alb['LoadBalancerArn'],
                    Attributes=[{
                        'Key': 'deletion_protection.enabled',
                        'Value': 'false',
                    }])
            self.manager.retry(
                client.delete_load_balancer, LoadBalancerArn=alb['LoadBalancerArn'])
        except Exception as e:
            if e.response['Error']['Code'] in ['OperationNotPermitted',
                                               'LoadBalancerNotFound']:
                self.log.warning(
                    "Exception trying to delete ALB: %s error: %s",
                    alb['LoadBalancerArn'], e)
                return
            raise


class AppELBListenerFilterBase(object):
    """ Mixin base class for filters that query LB listeners.
    """
    permissions = ("elasticloadbalancing:DescribeListeners",)

    def initialize(self, albs):
        def _process_listeners(alb):
            client = local_session(
                self.manager.session_factory).client('elbv2')
            results = client.describe_listeners(
                LoadBalancerArn=alb['LoadBalancerArn'])
            self.listener_map[alb['LoadBalancerArn']] = results['Listeners']

        self.listener_map = defaultdict(list)
        with self.manager.executor_factory(max_workers=2) as w:
            list(w.map(_process_listeners, albs))


class AppELBAttributeFilterBase(object):
    """ Mixin base class for filters that query LB attributes.
    """

    def initialize(self, albs):
        def _process_attributes(alb):
            if 'Attributes' not in alb:
                alb['Attributes'] = {}

                client = local_session(
                    self.manager.session_factory).client('elbv2')
                results = client.describe_load_balancer_attributes(
                    LoadBalancerArn=alb['LoadBalancerArn'])
                # flatten out the list of dicts and cast
                for pair in results['Attributes']:
                    k = pair['Key']
                    v = pair['Value']
                    if v.isdigit():
                        v = int(v)
                    elif v == 'true':
                        v = True
                    elif v == 'false':
                        v = False
                    alb['Attributes'][k] = v

        with self.manager.executor_factory(max_workers=2) as w:
            list(w.map(_process_attributes, albs))


@filters.register('is-logging')
class IsLoggingFilter(Filter, AppELBAttributeFilterBase):
    """ Matches AppELBs that are logging to S3.
        bucket and prefix are optional

    :example:

    .. code-block:: yaml

            policies:
                - name: alb-is-logging-test
                  resource: app-elb
                  filters:
                    - type: is-logging

                - name: alb-is-logging-bucket-and-prefix-test
                  resource: app-elb
                  filters:
                    - type: is-logging
                      bucket: prodlogs
                      prefix: alblogs

    """
    permissions = ("elasticloadbalancing:DescribeLoadBalancerAttributes",)
    schema = type_schema('is-logging',
                         bucket={'type': 'string'},
                         prefix={'type': 'string'}
                         )

    def process(self, resources, event=None):
        self.initialize(resources)
        bucket_name = self.data.get('bucket', None)
        bucket_prefix = self.data.get('prefix', None)

        return [alb for alb in resources
                if alb['Attributes']['access_logs.s3.enabled'] and
                (not bucket_name or bucket_name == alb['Attributes'].get(
                    'access_logs.s3.bucket', None)) and
                (not bucket_prefix or bucket_prefix == alb['Attributes'].get(
                    'access_logs.s3.prefix', None))
                ]


@filters.register('is-not-logging')
class IsNotLoggingFilter(Filter, AppELBAttributeFilterBase):
    """ Matches AppELBs that are NOT logging to S3.
        or do not match the optional bucket and/or prefix.

    :example:

    .. code-block:: yaml

            policies:
                - name: alb-is-not-logging-test
                  resource: app-elb
                  filters:
                    - type: is-not-logging

                - name: alb-is-not-logging-bucket-and-prefix-test
                  resource: app-elb
                  filters:
                    - type: is-not-logging
                      bucket: prodlogs
                      prefix: alblogs

    """
    permissions = ("elasticloadbalancing:DescribeLoadBalancerAttributes",)
    schema = type_schema('is-not-logging',
                         bucket={'type': 'string'},
                         prefix={'type': 'string'}
                         )

    def process(self, resources, event=None):
        self.initialize(resources)
        bucket_name = self.data.get('bucket', None)
        bucket_prefix = self.data.get('prefix', None)

        return [alb for alb in resources
                if not alb['Attributes']['access_logs.s3.enabled'] or
                (bucket_name and bucket_name != alb['Attributes'].get(
                    'access_logs.s3.bucket', None)) or
                (bucket_prefix and bucket_prefix != alb['Attributes'].get(
                    'access_logs.s3.prefix', None))
                ]


class AppELBTargetGroupFilterBase(object):
    """ Mixin base class for filters that query LB target groups.
    """

    def initialize(self, albs):
        self.target_group_map = defaultdict(list)
        target_groups = self.manager.get_resource_manager(
            'app-elb-target-group').resources()
        for target_group in target_groups:
            for load_balancer_arn in target_group['LoadBalancerArns']:
                self.target_group_map[load_balancer_arn].append(target_group)


@filters.register('listener')
class AppELBListenerFilter(ValueFilter, AppELBListenerFilterBase):
    """Filter ALB based on matching listener attributes

    Adding the `matched` flag will filter on previously matched listeners

    :example:

    .. code-block:: yaml

            policies:
              - name: app-elb-invalid-ciphers
                resource: app-elb
                filters:
                  - type: listener
                    key: Protocol
                    value: HTTPS
                  - type: listener
                    key: SslPolicy
                    value: ['ELBSecurityPolicy-TLS-1-1-2017-01','ELBSecurityPolicy-TLS-1-2-2017-01']
                    op: ni
                    matched: true
                actions:
                  - type: modify-listener
                    sslpolicy: "ELBSecurityPolicy-TLS-1-2-2017-01"
    """

    schema = type_schema(
        'listener', rinherit=ValueFilter.schema, matched={'type': 'boolean'})
    permissions = ("elasticloadbalancing:DescribeLoadBalancerAttributes",)

    def validate(self):
        if not self.data.get('matched'):
            return
        listeners = [f for f in self.manager.filters
                     if isinstance(f, self.__class__)]
        found = False
        for f in listeners[:listeners.index(self)]:
            if not f.data.get('matched', False):
                found = True
                break
        if not found:
            raise FilterValidationError(
                "matched listener filter, requires preceding listener filter")
        return self

    def process(self, albs, event=None):
        self.initialize(albs)
        return super(AppELBListenerFilter, self).process(albs, event)

    def __call__(self, alb):
        listeners = self.listener_map[alb['LoadBalancerArn']]
        if self.data.get('matched', False):
            listeners = alb.pop('c7n:MatchedListeners', [])

        found_listeners = False
        for listener in listeners:
            if self.match(listener):
                set_annotation(alb, 'c7n:MatchedListeners', listener)
                found_listeners = True
        return found_listeners


@actions.register('modify-listener')
class AppELBModifyListenerPolicy(BaseAction):
    """Action to modify the policy for an App ELB

    :example:

    .. code-block:: yaml

            policies:
              - name: appelb-modify-listener
                resource: app-elb
                filters:
                  - type: listener
                    key: Protocol
                    value: HTTP
                actions:
                  - type: modify-listener
                    protocol: HTTPS
                    sslpolicy: "ELBSecurityPolicy-TLS-1-2-2017-01"
                    certificate: "arn:aws:acm:region:123456789012:certificate/12345678-\
                    1234-1234-1234-123456789012"
    """

    schema = type_schema(
        'modify-listener',
        port={'type': 'integer'},
        protocol={'enum': ['HTTP', 'HTTPS']},
        sslpolicy={'type': 'string'},
        certificate={'type': 'string'}
    )

    permissions = ("elasticloadbalancing:ModifyListener",)

    def validate(self):
        for f in self.manager.data.get('filters', ()):
            if 'listener' in f.get('type', ()):
                return self
        raise FilterValidationError(
            "modify-listener action requires the listener filter")

    def process(self, load_balancers):
        args = {}
        if 'port' in self.data:
            args['Port'] = self.data.get('port')
        if 'protocol' in self.data:
            args['Protocol'] = self.data.get('protocol')
        if 'sslpolicy' in self.data:
            args['SslPolicy'] = self.data.get('sslpolicy')
        if 'certificate' in self.data:
            args['Certificates'] = [{'CertificateArn': self.data.get('certificate')}]
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_alb, load_balancers, itertools.repeat(args)))

    def process_alb(self, alb, args):
        client = local_session(self.manager.session_factory).client('elbv2')
        for matched_listener in alb.get('c7n:MatchedListeners', ()):
            client.modify_listener(
                ListenerArn=matched_listener['ListenerArn'],
                **args)


@filters.register('healthcheck-protocol-mismatch')
class AppELBHealthCheckProtocolMismatchFilter(Filter,
                                              AppELBTargetGroupFilterBase):
    """Filter AppELBs with mismatched health check protocols

    A mismatched health check protocol is where the protocol on the target group
    does not match the load balancer health check protocol

    :example:

    .. code-block:: yaml

            policies:
              - name: appelb-healthcheck-mismatch
                resource: app-elb
                filters:
                  - healthcheck-protocol-mismatch
    """

    schema = type_schema('healthcheck-protocol-mismatch')
    permissions = ("elasticloadbalancing:DescribeTargetGroups",)

    def process(self, albs, event=None):
        def _healthcheck_protocol_mismatch(alb):
            for target_group in self.target_group_map[alb['LoadBalancerArn']]:
                if (target_group['Protocol'] !=
                        target_group['HealthCheckProtocol']):
                    return True

            return False

        self.initialize(albs)
        return [alb for alb in albs if _healthcheck_protocol_mismatch(alb)]


@filters.register('target-group')
class AppELBTargetGroupFilter(ValueFilter, AppELBTargetGroupFilterBase):
    """Filter ALB based on matching target group value"""

    schema = type_schema('target-group', rinherit=ValueFilter.schema)
    permissions = ("elasticloadbalancing:DescribeTargetGroups",)

    def process(self, albs, event=None):
        self.initialize(albs)
        return super(AppELBTargetGroupFilter, self).process(albs, event)

    def __call__(self, alb):
        target_groups = self.target_group_map[alb['LoadBalancerArn']]
        return self.match(target_groups)


@filters.register('default-vpc')
class AppELBDefaultVpcFilter(DefaultVpcBase):
    """Filter all ELB that exist within the default vpc

    :example:

    .. code-block:: yaml

            policies:
              - name: appelb-in-default-vpc
                resource: app-elb
                filters:
                  - default-vpc
    """

    schema = type_schema('default-vpc')

    def __call__(self, alb):
        return alb.get('VpcId') and self.match(alb.get('VpcId')) or False


@resources.register('app-elb-target-group')
class AppELBTargetGroup(QueryResourceManager):
    """Resource manager for v2 ELB target groups.
    """

    class resource_type(object):

        service = 'elbv2'
        type = 'app-elb-target-group'
        enum_spec = ('describe_target_groups', 'TargetGroups', None)
        name = 'TargetGroupName'
        id = 'TargetGroupArn'
        filter_name = None
        filter_type = None
        dimension = None
        date = None

    filter_registry = FilterRegistry('app-elb-target-group.filters')
    action_registry = ActionRegistry('app-elb-target-group.actions')
    retry = staticmethod(get_retry(('Throttling',)))

    filter_registry.register('tag-count', tags.TagCountFilter)
    filter_registry.register('marked-for-op', tags.TagActionFilter)

    @classmethod
    def get_permissions(cls):
        # override as the service is not the iam prefix
        return ("elasticloadbalancing:DescribeTargetGroups",
                "elasticloadbalancing:DescribeTags")

    def augment(self, target_groups):
        def _describe_target_group_health(target_group):
            client = local_session(self.session_factory).client('elbv2')
            result = client.describe_target_health(
                TargetGroupArn=target_group['TargetGroupArn'])
            target_group['TargetHealthDescriptions'] = result[
                'TargetHealthDescriptions']

        with self.executor_factory(max_workers=2) as w:
            list(w.map(_describe_target_group_health, target_groups))

        _describe_target_group_tags(
            target_groups, self.session_factory,
            self.executor_factory, self.retry)
        return target_groups


def _describe_target_group_tags(target_groups, session_factory,
                                executor_factory, retry):
    def _process_tags(target_group_set):
        client = local_session(session_factory).client('elbv2')
        target_group_map = {
            target_group['TargetGroupArn']:
                target_group for target_group in target_group_set
        }

        results = retry(
            client.describe_tags,
            ResourceArns=list(target_group_map.keys()))
        for tag_desc in results['TagDescriptions']:
            if ('ResourceArn' in tag_desc and
                    tag_desc['ResourceArn'] in target_group_map):
                target_group_map[
                    tag_desc['ResourceArn']
                ]['Tags'] = tag_desc['Tags']

    with executor_factory(max_workers=2) as w:
        list(w.map(_process_tags, chunks(target_groups, 20)))


def _add_target_group_tags(target_groups, session_factory, ts):
    client = local_session(session_factory).client('elbv2')
    client.add_tags(
        ResourceArns=[
            target_group['TargetGroupArn'] for target_group in target_groups
        ],
        Tags=ts)


def _remove_target_group_tags(target_groups, session_factory, tag_keys):
    client = local_session(session_factory).client('elbv2')
    client.remove_tags(
        ResourceArns=[
            target_group['TargetGroupArn'] for target_group in target_groups
        ],
        TagKeys=tag_keys)


@AppELBTargetGroup.action_registry.register('mark-for-op')
class AppELBTargetGroupMarkForOpAction(tags.TagDelayedAction):
    """Action to specify a delayed action on an ELB target group"""

    batch_size = 1
    permissions = ("elasticloadbalancing:AddTags",)

    def process_resource_set(self, resource_set, ts):
        _add_target_group_tags(
            resource_set,
            self.manager.session_factory,
            ts)


@AppELBTargetGroup.action_registry.register('tag')
class AppELBTargetGroupTagAction(tags.Tag):
    """Action to create tag/tags on an ELB target group

    :example:

    .. code-block:: yaml

            policies:
              - name: appelb-targetgroup-add-required-tag
                resource: app-elb-target-group
                filters:
                  - "tag:RequiredTag": absent
                actions:
                  - type: tag
                    key: RequiredTag
                    value: RequiredValue
    """

    batch_size = 1
    permissions = ("elasticloadbalancing:AddTags",)

    def process_resource_set(self, resource_set, ts):
        _add_target_group_tags(
            resource_set,
            self.manager.session_factory,
            ts)


@AppELBTargetGroup.action_registry.register('remove-tag')
class AppELBTargetGroupRemoveTagAction(tags.RemoveTag):
    """Action to remove tag/tags from ELB target group

    :example:

    .. code-block:: yaml

            policies:
              - name: appelb-targetgroup-remove-expired-tag
                resource: app-elb-target-group
                filters:
                  - "tag:ExpiredTag": present
                actions:
                  - type: remove-tag
                    tags: ["ExpiredTag"]
    """

    batch_size = 1
    permissions = ("elasticloadbalancing:RemoveTags",)

    def process_resource_set(self, resource_set, tag_keys):
        _remove_target_group_tags(
            resource_set,
            self.manager.session_factory,
            tag_keys)


@AppELBTargetGroup.filter_registry.register('default-vpc')
class AppELBTargetGroupDefaultVpcFilter(DefaultVpcBase):
    """Filter all application elb target groups within the default vpc

    :example:

    .. code-block:: yaml

            policies:
              - name: appelb-targetgroups-default-vpc
                resource: app-elb-target-group
                filters:
                  - default-vpc
    """

    schema = type_schema('default-vpc')

    def __call__(self, target_group):
        return (target_group.get('VpcId') and
                self.match(target_group.get('VpcId')) or False)


@AppELBTargetGroup.action_registry.register('delete')
class AppELBTargetGroupDeleteAction(BaseAction):
    """Action to delete ELB target group

    It is recommended to apply a filter to the delete policy to avoid unwanted
    deletion of any app elb target groups.

    :example:

    .. code-block:: yaml

            policies:
              - name: appelb-targetgroups-delete-unused
                resource: app-elb-target-group
                filters:
                  - "tag:SomeTag": absent
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('elasticloadbalancing:DeleteTargetGroup',)

    def process(self, target_group):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_targetgroup, target_group))

    def process_targetgroup(self, target_group):
        client = local_session(self.manager.session_factory).client('elbv2')
        self.manager.retry(
            client.delete_target_group,
            TargetGroupArn=target_group['TargetGroupArn'])
