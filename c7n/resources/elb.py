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
Elastic Load Balancers
"""
from concurrent.futures import as_completed
import logging

from botocore.exceptions import ClientError

from c7n.actions import ActionRegistry, BaseAction, AutoTagUser
from c7n.filters import (
    Filter, FilterRegistry, FilterValidationError, DefaultVpcBase, ValueFilter)
import c7n.filters.vpc as net_filters
from c7n import tags
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, chunks, type_schema, get_retry

log = logging.getLogger('custodian.elb')

filters = FilterRegistry('elb.filters')
actions = ActionRegistry('elb.actions')

actions.register('auto-tag-user', AutoTagUser)
filters.register('tag-count', tags.TagCountFilter)
filters.register('marked-for-op', tags.TagActionFilter)


@resources.register('elb')
class ELB(QueryResourceManager):

    resource_type = "aws.elb.loadbalancer"
    filter_registry = filters
    action_registry = actions
    retry = staticmethod(get_retry(('Throttling',)))

    def augment(self, resources):
        _elb_tags(
            resources, self.session_factory, self.executor_factory, self.retry)
        return resources


def _elb_tags(elbs, session_factory, executor_factory, retry):

    def process_tags(elb_set):
        client = local_session(session_factory).client('elb')
        elb_map = {elb['LoadBalancerName']: elb for elb in elb_set}

        while True:
            try:
                results = retry(
                    client.describe_tags,
                    LoadBalancerNames=elb_map.keys())
                break
            except ClientError as e:
                if e.response['Error']['Code'] != 'LoadBalancerNotFound':
                    raise
                msg = e.response['Error']['Message']
                _, lb_name = msg.strip().rsplit(' ', 1)
                elb_map.pop(lb_name)
                if not elb_map:
                    results = {'TagDescriptions': []}
                    break
                continue
        for tag_desc in results['TagDescriptions']:
            elb_map[tag_desc['LoadBalancerName']]['Tags'] = tag_desc['Tags']

    with executor_factory(max_workers=2) as w:
        list(w.map(process_tags, chunks(elbs, 20)))


@actions.register('mark-for-op')
class TagDelayedAction(tags.TagDelayedAction):

    batch_size = 1

    def process_resource_set(self, resource_set, tags):
        client = local_session(self.manager.session_factory).client('elb')
        client.add_tags(
            LoadBalancerNames=[r['LoadBalancerName'] for r in resource_set],
            Tags=tags)


@actions.register('tag')
class Tag(tags.Tag):

    batch_size = 1

    def process_resource_set(self, resource_set, tags):
        client = local_session(
            self.manager.session_factory).client('elb')
        client.add_tags(
            LoadBalancerNames=[r['LoadBalancerName'] for r in resource_set],
            Tags=tags)


@actions.register('remove-tag')
class RemoveTag(tags.RemoveTag):

    batch_size = 1

    def process_resource_set(self, resource_set, tag_keys):
        client = local_session(
            self.manager.session_factory).client('elb')
        client.remove_tags(
            LoadBalancerNames=[r['LoadBalancerName'] for r in resource_set],
            Tags=[{'Key': k for k in tag_keys}])


@actions.register('delete')
class Delete(BaseAction):

    schema = type_schema('delete')

    def process(self, load_balancers):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_elb, load_balancers))

    def process_elb(self, elb):
        client = local_session(self.manager.session_factory).client('elb')
        client.delete_load_balancer(LoadBalancerName=elb['LoadBalancerName'])


@actions.register('set-ssl-listener-policy')
class SetSslListenerPolicy(BaseAction):

    schema = type_schema(
        'set-ssl-listener-policy',
        name={'type': 'string'},
        attributes={'type': 'array', 'items': {'type': 'string'}},
        required=['name', 'attributes'])

    def process(self, load_balancers):
        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_elb, load_balancers))

    def process_elb(self, elb):
        if not is_ssl(elb):
            return

        client = local_session(self.manager.session_factory).client('elb')

        # Create a custom policy.
        attrs = self.data.get('attributes')
        # This name must be unique within the
        # set of policies for this load balancer.
        policy_name = self.data.get('name')
        lb_name = elb['LoadBalancerName']
        policy_attributes = [{'AttributeName': attr, 'AttributeValue': 'true'}
            for attr in attrs]

        try:
            client.create_load_balancer_policy(
                LoadBalancerName=lb_name,
                PolicyName=policy_name,
                PolicyTypeName='SSLNegotiationPolicyType',
                PolicyAttributes=policy_attributes)
        except ClientError as e:
            if e.response['Error']['Code'] != 'DuplicatePolicyName':
                raise

        # Apply it to all SSL listeners.
        for ld in elb['ListenerDescriptions']:
            if ld['Listener']['Protocol'] in ('HTTPS', 'SSL'):
                client.set_load_balancer_policies_of_listener(
                    LoadBalancerName=lb_name,
                    LoadBalancerPort=ld['Listener']['LoadBalancerPort'],
                    PolicyNames=[policy_name])


def is_ssl(b):
    for ld in b['ListenerDescriptions']:
        if ld['Listener']['Protocol'] in ('HTTPS', 'SSL'):
            return True
    return False


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[]"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "Subnets[]"


@filters.register('instance')
class Instance(ValueFilter):

    schema = type_schema(
        'instance', rinherit=ValueFilter.schema)

    annotate = False

    def process(self, resources, event=None):
        instances = []
        for r in resources:
            instances.extend([i['InstanceId'] for i in r['Instances']])
        instances = set(instances)
        from c7n.resources.ec2 import EC2
        manager = EC2(self.manager.ctx, {})

        self.elb_instances = {}
        for i in manager.resources():
            if i['InstanceId'] in instances:
                self.elb_instances[i['InstanceId']] = i
        return super(Instance, self).process(resources, event)

    def __call__(self, elb):
        matched = []
        for i in elb['Instances']:
            instance = self.elb_instances[i['InstanceId']]
            if not instance.get('IamInstanceProfile'):
                print instance['InstanceId']
                #import pdb; pdb.set_trace()
            if self.match(instance):
                matched.append(instance)
        if not matched:
            return False
        elb['MatchedInstances'] = matched
        return True


@filters.register('is-ssl')
class IsSSLFilter(Filter):

    schema = type_schema('is-ssl')

    def process(self, balancers, event=None):
        return [b for b in balancers if is_ssl(b)]


@filters.register('ssl-policy')
class SSLPolicyFilter(Filter):
    """Filter ELBs on the properties of SSLNegotation policies.
    TODO: Only works on custom policies at the moment.

    filters:
      - type: ssl-policy

        whitelist: []
        blacklist:
        - "Protocol-SSLv2"
        - "Protocol-SSLv3"
    """

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'oneOf': [
            {'required': ['type', 'whitelist']},
            {'required': ['type', 'blacklist']}
            ],
        'properties': {
            'type': {'enum': ['ssl-policy']},
            'whitelist': {'type': 'array', 'items': {'type': 'string'}},
            'blacklist': {'type': 'array', 'items': {'type': 'string'}}
            }
        }

    def validate(self):
        if 'whitelist' in self.data and 'blacklist' in self.data:
            raise FilterValidationError(
                "cannot specify whitelist and black list")

        if 'whitelist' not in self.data and 'blacklist' not in self.data:
            raise FilterValidationError(
                "must specify either policy blacklist or whitelist")
        if ('blacklist' in self.data and
                not isinstance(self.data['blacklist'], list)):
            raise FilterValidationError("blacklist must be a list")

        return self

    def process(self, balancers, event=None):
        balancers = [b for b in balancers if is_ssl(b)]
        active_policy_attribute_tuples = (
            self.create_elb_active_policy_attribute_tuples(balancers))

        whitelist = set(self.data.get('whitelist', []))
        blacklist = set(self.data.get('blacklist', []))

        invalid_elbs = []

        if blacklist:
            for elb, active_policies in active_policy_attribute_tuples:
                if len(blacklist.intersection(active_policies)) > 0:
                    elb["ProhibitedPolicies"] = list(blacklist.intersection(active_policies))
                    invalid_elbs.append(elb)
        elif whitelist:
            for elb, active_policies in active_policy_attribute_tuples:
                if len(set(active_policies).difference(whitelist)) > 0:
                    elb["ProhibitedPolicies"] = list(set(active_policies).difference(whitelist))
                    invalid_elbs.append(elb)
        return invalid_elbs

    def create_elb_active_policy_attribute_tuples(self, elbs):
        """
        Returns a list of tuples of active SSL policies attributes
        for each elb [(elb['Protocol-SSLv1','Protocol-SSLv2',...])]
        """

        elb_custom_policy_tuples = self.create_elb_custom_policy_tuples(elbs)

        active_policy_attribute_tuples = (
            self.create_elb_active_attributes_tuples(elb_custom_policy_tuples))

        return active_policy_attribute_tuples

    def create_elb_custom_policy_tuples(self, balancers):
        """
        creates a list of tuples (elb,[sslpolicy1,sslpolicy2...])
        for all custom policies on the ELB
        """
        elb_policy_tuples = []
        for b in balancers:
            policies = []
            for ld in b['ListenerDescriptions']:
                for p in ld['PolicyNames']:
                    policies.append(p)
            elb_policy_tuples.append((b, policies))

        return elb_policy_tuples

    def create_elb_active_attributes_tuples(self, elb_policy_tuples):
        """
        creates a list of tuples for all attributes that are marked
        as "true" in the load balancer's polices, e.g.
        (myelb,['Protocol-SSLv1','Protocol-SSLv2'])
        """
        active_policy_attribute_tuples = []
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for elb_policy_set in chunks(elb_policy_tuples, 50):
                futures.append(
                    w.submit(self.process_elb_policy_set, elb_policy_set))

            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception processing elb policies \n %s" % (
                            f.exception()))
                    continue
                for elb_policies in f.result():
                    active_policy_attribute_tuples.append(elb_policies)

        return active_policy_attribute_tuples

    def process_elb_policy_set(self, elb_policy_set):
        results = []
        client = local_session(self.manager.session_factory).client('elb')

        for (elb, policy_names) in elb_policy_set:
            elb_name = elb['LoadBalancerName']
            try:
                policies = client.describe_load_balancer_policies(
                    LoadBalancerName=elb_name,
                    PolicyNames=policy_names)['PolicyDescriptions']
            except ClientError as e:
                if e.response['Error']['Code'] in [
                        'LoadBalancerNotFound', 'PolicyNotFound']:
                    continue
                raise
            active_lb_policies = []
            for p in policies:
                if p['PolicyTypeName'] != 'SSLNegotiationPolicyType':
                    continue
                active_lb_policies.extend(
                    [policy_description['AttributeName']
                     for policy_description in
                     p['PolicyAttributeDescriptions']
                     if policy_description['AttributeValue'] == 'true']
                )
            results.append((elb, active_lb_policies))

        return results


@filters.register('healthcheck-protocol-mismatch')
class HealthCheckProtocolMismatch(Filter):
    """
    """

    schema = type_schema('healthcheck-protocol-mismatch')

    def __call__(self, load_balancer):
        health_check_protocol = (
            load_balancer['HealthCheck']['Target'].split(':')[0])
        listener_descriptions = load_balancer['ListenerDescriptions']

        if len(listener_descriptions) == 0:
            return True

        # check if any of the protocols in the ELB match the health
        # check. There is only 1 health check, so if there are
        # multiple listeners, we only check if at least one of them
        # matches
        protocols = [listener['Listener']['InstanceProtocol']
                     for listener in listener_descriptions]
        return health_check_protocol in protocols


@filters.register('default-vpc')
class DefaultVpc(DefaultVpcBase):
    """ Matches if an elb database is in the default vpc
    """

    schema = type_schema('default-vpc')

    def __call__(self, elb):
        return elb.get('VPCId') and self.match(elb.get('VPCId')) or False
