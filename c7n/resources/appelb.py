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
import logging

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import Filter, FilterRegistry, DefaultVpcBase, OPERATORS
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

    class Meta(object):

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

    resource_type = Meta
    filter_registry = filters
    action_registry = actions
    retry = staticmethod(get_retry(('Throttling',)))

    def augment(self, albs):
        _describe_appelb_tags(
            albs, self.session_factory, self.executor_factory, self.retry)

        return albs


def _describe_appelb_tags(albs, session_factory, executor_factory, retry):
    def _process_tags(alb_set):
        client = local_session(session_factory).client('elbv2')
        alb_map = {alb['LoadBalancerArn']: alb for alb in alb_set}

        results = retry(client.describe_tags, ResourceArns=alb_map.keys())
        for tag_desc in results['TagDescriptions']:
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


@actions.register('mark-for-op')
class AppELBMarkForOpAction(tags.TagDelayedAction):

    batch_size = 1

    def process_resource_set(self, resource_set, ts):
        _add_appelb_tags(
            resource_set,
            self.manager.session_factory,
            ts)


@actions.register('tag')
class AppELBTagAction(tags.Tag):

    batch_size = 1

    def process_resource_set(self, resource_set, ts):
        _add_appelb_tags(
            resource_set,
            self.manager.session_factory,
            ts)


@actions.register('remove-tag')
class AppELBRemoveTagAction(tags.RemoveTag):

    batch_size = 1

    def process_resource_set(self, resource_set, tag_keys):
        _remove_appelb_tags(
            resource_set,
            self.manager.session_factory,
            tag_keys)


@actions.register('delete')
class AppELBDeleteAction(BaseAction):

    schema = type_schema('delete')

    def process(self, load_balancers):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_alb, load_balancers))

    def process_alb(self, alb):
        client = local_session(self.manager.session_factory).client('elbv2')
        client.delete_load_balancer(LoadBalancerArn=alb['LoadBalancerArn'])


class AppELBListenerFilter(Filter):
    """ Base class for filters that query LB listeners.
    """
    def initialize(self, albs):
        def _process_listeners(alb):
            if 'Listeners' not in alb:
                client = local_session(
                    self.manager.session_factory).client('elbv2')
                results = client.describe_listeners(
                    LoadBalancerArn=alb['LoadBalancerArn'])
                alb['Listeners'] = results['Listeners']

        with self.manager.executor_factory(max_workers=2) as w:
            list(w.map(_process_listeners, albs))


class AppELBAttributeFilter(Filter):
    """ Base class for filters that query LB attributes.
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


class AppELBTargetGroupFilter(Filter):
    """ Base class for filters that query LB target groups.
    """
    def initialize(self, albs):
        def _process_target_groups(alb):
            if 'TargetGroups' not in alb:
                client = local_session(
                    self.manager.session_factory).client('elbv2')
                results = client.describe_target_groups(
                    LoadBalancerArn=alb['LoadBalancerArn'])
                alb['TargetGroups'] = results['TargetGroups']

                for target_group in alb['TargetGroups']:
                    result = client.describe_target_health(
                        TargetGroupArn=target_group['TargetGroupArn'])
                    target_group['TargetHealthDescriptions'] = result[
                        'TargetHealthDescriptions']

        with self.manager.executor_factory(max_workers=2) as w:
            list(w.map(_process_target_groups, albs))


@filters.register('is-https')
class AppELBIsHTTPSFilter(AppELBListenerFilter):
    """
    """

    schema = type_schema('is-https')

    def process(self, albs, event=None):
        def _is_https(alb):
            for listener in alb.get('Listeners', []):
                if listener['Protocol'] == 'HTTPS':
                    return True
            return False

        self.initialize(albs)
        return [alb for alb in albs if _is_https(alb)]


@filters.register('healthcheck-protocol-mismatch')
class AppELBHealthCheckProtocolMismatchFilter(AppELBTargetGroupFilter):
    """
    """

    schema = type_schema('healthcheck-protocol-mismatch')

    def process(self, albs, event=None):
        def _healthcheck_protocol_mismatch(alb):
            for target_group in alb['TargetGroups']:
                if (target_group['Protocol'] !=
                        target_group['HealthCheckProtocol']):
                    return True

            return False

        self.initialize(albs)
        return [alb for alb in albs if _healthcheck_protocol_mismatch(alb)]


@filters.register('instance-count')
class AppELBInstanceCountFilter(AppELBTargetGroupFilter):
    """
    """

    schema = type_schema(
        'instance-count',
        count={'type': 'integer', 'minimum': 0},
        op={'enum': OPERATORS.keys()})

    def process(self, albs, event=None):
        def _instance_count(alb, count, op):
            instance_count = 0
            for target_group in alb['TargetGroups']:
                instance_count += len(target_group['TargetHealthDescriptions'])
            return op(instance_count, count)

        self.initialize(albs)
        count = self.data.get('count', 0)
        op_name = self.data.get('op', 'eq')
        op = OPERATORS.get(op_name)
        return [alb for alb in albs if _instance_count(alb, count, op)]


@filters.register('default-vpc')
class AppELBDefaultVpcFilter(DefaultVpcBase):

    schema = type_schema('default-vpc')

    def __call__(self, alb):
        return alb.get('VpcId') and self.match(alb.get('VpcId')) or False


@resources.register('app-elb-target-group')
class AppELBTargetGroup(QueryResourceManager):
    """Resource manager for v2 ELB target groups.
    """

    class Meta(object):

        service = 'elbv2'
        type = 'app-elb-target-group'
        enum_spec = ('describe_target_groups', 'TargetGroups', None)
        name = 'TargetGroupName'
        id = 'TargetGroupArn'
        filter_name = None
        filter_type = None
        dimension = None
        date = None

    resource_type = Meta
    filter_registry = FilterRegistry('app-elb-target-group.filters')
    action_registry = ActionRegistry('app-elb-target-group.actions')
    retry = staticmethod(get_retry(('Throttling',)))


@AppELBTargetGroup.filter_registry.register('default-vpc')
class AppELBTargetGroupDefaultVpcFilter(DefaultVpcBase):

    schema = type_schema('default-vpc')

    def __call__(self, target_group):
        return (target_group.get('VpcId') and
                self.match(target_group.get('VpcId')) or False)
