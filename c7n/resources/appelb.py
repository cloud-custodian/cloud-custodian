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
"""
Application Load Balancers
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from collections import defaultdict
from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import (
    Filter, FilterRegistry, FilterValidationError, DefaultVpcBase, ValueFilter)
import c7n.filters.vpc as net_filters
from c7n import tags
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, chunks, type_schema, get_retry

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
        type = 'app-elb'
        enum_spec = ('describe_load_balancers', 'LoadBalancers', None)
        name = 'LoadBalancerName'
        id = 'LoadBalancerArn'
        filter_name = None
        filter_type = None
        dimension = None
        date = 'CreatedTime'
        config_type = 'AWS::ElasticLoadBalancingV2::LoadBalancer'

    filter_registry = filters
    action_registry = actions
    retry = staticmethod(get_retry(('Throttling',)))

    @classmethod
    def get_permissions(cls):
        # override as the service is not the iam prefix
        return ("elasticloadbalancing:DescribeLoadBalancers",
                "elasticloadbalancing:DescribeTags")

    def augment(self, albs):
        _describe_appelb_tags(
            albs, self.session_factory,
            self.executor_factory, self.retry)

        return albs


def _describe_appelb_tags(albs, session_factory, executor_factory, retry):
    def _process_tags(alb_set):
        client = local_session(session_factory).client('elbv2')
        alb_map = {alb['LoadBalancerArn']: alb for alb in alb_set}

        results = retry(client.describe_tags, ResourceArns=alb_map.keys())
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


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[]"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "AvailabilityZones[].SubnetId"


filters.register('network-location', net_filters.NetworkLocation)


@actions.register('mark-for-op')
class AppELBMarkForOpAction(tags.TagDelayedAction):
    """Action to create a delayed action on an ELB to start at a later date

    :example:

        .. code-block: yaml

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

        .. code-block: yaml

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

        .. code-block: yaml

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

        .. code-block: yaml

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
                client = local_session(
                    self.manager.session_factory).client('elbv2')
                results = client.describe_load_balancer_attributes(
                    LoadBalancerArn=alb['LoadBalancerArn'])
                alb['Attributes'] = results['Attributes']

        with self.manager.executor_factory(max_workers=2) as w:
            list(w.map(_process_attributes, albs))


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
    """Filter ALB based on matching listener attributes"""

    schema = type_schema('listener', rinherit=ValueFilter.schema)
    permissions = ("elasticloadbalancing:DescribeLoadBalancerAttributes",)

    def process(self, albs, event=None):
        self.initialize(albs)
        return super(AppELBListenerFilter, self).process(albs, event)

    def __call__(self, alb):
        matched = []
        for listener in self.listener_map[alb['LoadBalancerArn']]:
            if self.match(listener):
                matched.append(listener)
        if not matched:
            return False
        alb['c7n:MatchedListeners'] = matched
        return True


@actions.register('modify-listener')
class AppELBModifyListenerPolicy(BaseAction):
    """Action to modify the policy for an App ELB

    :example:

        .. code-block: yaml

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
            list(w.map(self.process_alb, load_balancers, [args]))

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

        .. code-block: yaml

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

        .. code-block: yaml

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
            ResourceArns=target_group_map.keys())
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

        .. code-block: yaml

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

        .. code-block: yaml

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

        .. code-block: yaml

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
