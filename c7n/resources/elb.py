# Copyright 2015-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from concurrent.futures import as_completed
import logging
import re

from botocore.exceptions import ClientError

from c7n.actions import ActionRegistry, BaseAction, ModifyVpcSecurityGroupsAction
from c7n.exceptions import PolicyValidationError
from c7n.filters import (
    Filter, FilterRegistry, DefaultVpcBase, ValueFilter,
    ShieldMetrics)
import c7n.filters.vpc as net_filters
from datetime import datetime
from dateutil.tz import tzutc
from c7n import tags
from c7n.manager import resources
from c7n.query import QueryResourceManager, DescribeSource
from c7n.utils import local_session, chunks, type_schema, get_retry, worker

from c7n.resources.shield import IsShieldProtected, SetShieldProtection

log = logging.getLogger('custodian.elb')

filters = FilterRegistry('elb.filters')
actions = ActionRegistry('elb.actions')

filters.register('tag-count', tags.TagCountFilter)
filters.register('marked-for-op', tags.TagActionFilter)
filters.register('shield-enabled', IsShieldProtected)
filters.register('shield-metrics', ShieldMetrics)


@resources.register('elb')
class ELB(QueryResourceManager):

    class resource_type(object):
        service = 'elb'
        resource_type = 'elasticloadbalancing:loadbalancer'
        type = 'loadbalancer'
        enum_spec = ('describe_load_balancers',
                     'LoadBalancerDescriptions', None)
        detail_spec = None
        id = 'LoadBalancerName'
        filter_name = 'LoadBalancerNames'
        filter_type = 'list'
        name = 'DNSName'
        date = 'CreatedTime'
        dimension = 'LoadBalancerName'
        config_type = "AWS::ElasticLoadBalancing::LoadBalancer"
        default_report_fields = (
            'LoadBalancerName',
            'DNSName',
            'VPCId',
            'count:Instances',
            'list:ListenerDescriptions[].Listener.LoadBalancerPort')

    filter_registry = filters
    action_registry = actions
    retry = staticmethod(get_retry(('Throttling',)))

    @classmethod
    def get_permissions(cls):
        return ('elasticloadbalancing:DescribeLoadBalancers',
                'elasticloadbalancing:DescribeLoadBalancerAttributes',
                'elasticloadbalancing:DescribeTags')

    def get_arn(self, r):
        return "arn:aws:elasticloadbalancing:%s:%s:loadbalancer/%s" % (
            self.config.region,
            self.config.account_id,
            r[self.resource_type.id])

    def get_arns(self, resources):
        return map(self.get_arn, resources)

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeELB(self)
        return super(ELB, self).get_source(source_type)


class DescribeELB(DescribeSource):

    def augment(self, resources):
        return tags.universal_augment(self.manager, resources)


@actions.register('set-shield')
class SetELBShieldProtection(SetShieldProtection):

    def clear_stale(self, client, protections):
        # elbs arns need extra discrimination to distinguish
        # from app load balancer arns. See https://goo.gl/pE7TQb
        super(SetELBShieldProtection, self).clear_stale(
            client,
            [p for p in protections if p['ResourceArn'].count('/') == 1])


@actions.register('mark-for-op')
class TagDelayedAction(tags.TagDelayedAction):
    """Action to specify an action to occur at a later date

    :example:

    .. code-block:: yaml

            policies:
              - name: elb-delete-unused
                resource: elb
                filters:
                  - "tag:custodian_cleanup": absent
                  - Instances: []
                actions:
                  - type: mark-for-op
                    tag: custodian_cleanup
                    msg: "Unused ELB - No Instances: {op}@{action_date}"
                    op: delete
                    days: 7
    """

    batch_size = 1
    permissions = ('elasticloadbalancing:AddTags',)

    def process_resource_set(self, resource_set, tags):
        client = local_session(self.manager.session_factory).client('elb')
        client.add_tags(
            LoadBalancerNames=[r['LoadBalancerName'] for r in resource_set],
            Tags=tags)


@actions.register('tag')
class Tag(tags.Tag):
    """Action to add tag(s) to ELB(s)

    :example:

    .. code-block:: yaml

            policies:
              - name: elb-add-owner-tag
                resource: elb
                filters:
                  - "tag:OwnerName": missing
                actions:
                  - type: tag
                    key: OwnerName
                    value: OwnerName
    """

    batch_size = 1
    permissions = ('elasticloadbalancing:AddTags',)

    def process_resource_set(self, resource_set, tags):
        client = local_session(
            self.manager.session_factory).client('elb')
        client.add_tags(
            LoadBalancerNames=[r['LoadBalancerName'] for r in resource_set],
            Tags=tags)


@actions.register('remove-tag')
class RemoveTag(tags.RemoveTag):
    """Action to remove tag(s) from ELB(s)

    :example:

    .. code-block:: yaml

            policies:
              - name: elb-remove-old-tag
                resource: elb
                filters:
                  - "tag:OldTagKey": present
                actions:
                  - type: remove-tag
                    tags: [OldTagKey1, OldTagKey2]
    """

    batch_size = 1
    permissions = ('elasticloadbalancing:RemoveTags',)

    def process_resource_set(self, resource_set, tag_keys):
        client = local_session(
            self.manager.session_factory).client('elb')
        client.remove_tags(
            LoadBalancerNames=[r['LoadBalancerName'] for r in resource_set],
            Tags=[{'Key': k for k in tag_keys}])


@actions.register('delete')
class Delete(BaseAction):
    """Action to delete ELB(s)

    It is recommended to apply a filter to the delete policy to avoid unwanted
    deletion of any load balancers.

    :example:

    .. code-block:: yaml

            policies:
              - name: elb-delete-unused
                resource: elb
                filters:
                  - Instances: []
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('elasticloadbalancing:DeleteLoadBalancer',)

    def process(self, load_balancers):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_elb, load_balancers))

    def process_elb(self, elb):
        client = local_session(self.manager.session_factory).client('elb')
        self.manager.retry(
            client.delete_load_balancer,
            LoadBalancerName=elb['LoadBalancerName'])


@actions.register('set-ssl-listener-policy')
class SetSslListenerPolicy(BaseAction):
    """Action to set the ELB SSL listener policy

    :example:

    .. code-block:: yaml

            policies:
              - name: elb-set-listener-policy
                resource: elb
                actions:
                  - type: set-ssl-listener-policy
                    name: SSLNegotiation-Policy-01
                    attributes:
                      - Protocol-SSLv3
                      - Protocol-TLSv1.1
                      - DHE-RSA-AES256-SHA256
    """

    schema = type_schema(
        'set-ssl-listener-policy',
        name={'type': 'string'},
        attributes={'type': 'array', 'items': {'type': 'string'}},
        required=['name', 'attributes'])

    permissions = (
        'elasticloadbalancing:CreateLoadBalancerPolicy',
        'elasticloadbalancing:SetLoadBalancerPoliciesOfListener')

    def process(self, load_balancers):
        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_elb, load_balancers))

    @worker
    def process_elb(self, elb):
        if not is_ssl(elb):
            return

        client = local_session(self.manager.session_factory).client('elb')

        # Create a custom policy with epoch timestamp.
        # to make it unique within the
        # set of policies for this load balancer.
        policy_name = self.data.get('name') + '-' + \
            str(int(datetime.now(tz=tzutc()).strftime("%s")) * 1000)
        lb_name = elb['LoadBalancerName']
        attrs = self.data.get('attributes')
        policy_attributes = [{'AttributeName': attr, 'AttributeValue': 'true'}
            for attr in attrs]

        try:
            client.create_load_balancer_policy(
                LoadBalancerName=lb_name,
                PolicyName=policy_name,
                PolicyTypeName='SSLNegotiationPolicyType',
                PolicyAttributes=policy_attributes)
        except ClientError as e:
            if e.response['Error']['Code'] not in (
                    'DuplicatePolicyName', 'DuplicatePolicyNameException',
                    'DuplicationPolicyNameException'):
                raise

        # Apply it to all SSL listeners.
        ssl_policies = ()
        if 'c7n.ssl-policies' in elb:
            ssl_policies = elb['c7n.ssl-policies']

        for ld in elb['ListenerDescriptions']:
            if ld['Listener']['Protocol'] in ('HTTPS', 'SSL'):
                policy_names = [policy_name]
                # Preserve extant non-ssl listener policies
                policy_names.extend(ld.get('PolicyNames', ()))
                # Remove extant ssl listener policy
                if ssl_policies:
                    policy_names = list(set(policy_names).difference(ssl_policies))
                client.set_load_balancer_policies_of_listener(
                    LoadBalancerName=lb_name,
                    LoadBalancerPort=ld['Listener']['LoadBalancerPort'],
                    PolicyNames=policy_names)


@actions.register('modify-security-groups')
class ELBModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):
    """Modify VPC security groups on an ELB."""

    permissions = ('elasticloadbalancing:ApplySecurityGroupsToLoadBalancer',)

    def process(self, load_balancers):
        client = local_session(self.manager.session_factory).client('elb')
        groups = super(ELBModifyVpcSecurityGroups, self).get_groups(
            load_balancers, 'SecurityGroups')
        for idx, l in enumerate(load_balancers):
            client.apply_security_groups_to_load_balancer(
                LoadBalancerName=l['LoadBalancerName'],
                SecurityGroups=groups[idx])


@actions.register('enable-s3-logging')
class EnableS3Logging(BaseAction):
    """Action to enable S3 logging for Elastic Load Balancers.

    :example:

    .. code-block:: yaml

            policies:
              - name: elb-test
                resource: app-elb
                filters:
                  - type: is-not-logging
                actions:
                  - type: enable-s3-logging
                    bucket: elblogtest
                    prefix: dahlogs
                    emit_interval: 5
    """
    schema = type_schema('enable-s3-logging',
        bucket={'type': 'string'},
        prefix={'type': 'string'},
        emit_interval={'type': 'integer'},
    )
    permissions = ("elasticloadbalancing:ModifyLoadBalancerAttributes",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('elb')
        for elb in resources:
            elb_name = elb['LoadBalancerName']
            log_attrs = {'Enabled': True}
            if 'bucket' in self.data:
                log_attrs['S3BucketName'] = self.data['bucket']
            if 'prefix' in self.data:
                log_attrs['S3BucketPrefix'] = self.data['prefix']
            if 'emit_interval' in self.data:
                log_attrs['EmitInterval'] = self.data['emit_interval']

            client.modify_load_balancer_attributes(LoadBalancerName=elb_name,
                                                   LoadBalancerAttributes={
                                                       'AccessLog': log_attrs
                                                   })
        return resources


@actions.register('disable-s3-logging')
class DisableS3Logging(BaseAction):
    """Disable s3 logging for ElasticLoadBalancers.

    :example:

    .. code-block:: yaml

            policies:
              - name: turn-off-elb-logs
                resource: elb
                filters:
                  - type: is-logging
                    bucket: prodbucket
                actions:
                  - type: disable-elb-logging
    """
    schema = type_schema('disable-s3-logging')
    permissions = ("elasticloadbalancing:ModifyLoadBalancerAttributes",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('elb')
        for elb in resources:
            elb_name = elb['LoadBalancerName']
            client.modify_load_balancer_attributes(LoadBalancerName=elb_name,
                                                   LoadBalancerAttributes={
                                                       'AccessLog': {
                                                           'Enabled': False}
                                                   })
        return resources


def is_ssl(b):
    for ld in b['ListenerDescriptions']:
        if ld['Listener']['Protocol'] in ('HTTPS', 'SSL'):
            return True
    return False


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):
    """ELB security group filter"""

    RelatedIdsExpression = "SecurityGroups[]"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):
    """ELB subnet filter"""

    RelatedIdsExpression = "Subnets[]"


filters.register('network-location', net_filters.NetworkLocation)


@filters.register('instance')
class Instance(ValueFilter):
    """Filter ELB by an associated instance value(s)

    :example:

    .. code-block:: yaml

            policies:
              - name: elb-image-filter
                resource: elb
                filters:
                  - type: instance
                    key: ImageId
                    value: ami-01ab23cd
    """

    schema = type_schema('instance', rinherit=ValueFilter.schema)
    annotate = False

    def get_permissions(self):
        return self.manager.get_resource_manager('ec2').get_permissions()

    def process(self, resources, event=None):
        self.elb_instances = {}
        instances = []
        for r in resources:
            instances.extend([i['InstanceId'] for i in r['Instances']])
        for i in self.manager.get_resource_manager(
                'ec2').get_resources(list(instances)):
            self.elb_instances[i['InstanceId']] = i
        return super(Instance, self).process(resources, event)

    def __call__(self, elb):
        matched = []
        for i in elb['Instances']:
            instance = self.elb_instances[i['InstanceId']]
            if self.match(instance):
                matched.append(instance)
        if not matched:
            return False
        elb['c7n:MatchedInstances'] = matched
        return True


@filters.register('is-ssl')
class IsSSLFilter(Filter):
    """Filters ELB that are using a SSL policy

    :example:

    .. code-block:: yaml

            policies:
              - name: elb-using-ssl
                resource: elb
                filters:
                  - type: is-ssl
    """

    schema = type_schema('is-ssl')

    def process(self, balancers, event=None):
        return [b for b in balancers if is_ssl(b)]


@filters.register('ssl-policy')
class SSLPolicyFilter(Filter):
    """Filter ELBs on the properties of SSLNegotation policies.
    TODO: Only works on custom policies at the moment.

    whitelist: filter all policies containing permitted protocols
    blacklist: filter all policies containing forbidden protocols

    Cannot specify both whitelist & blacklist in the same policy. These must
    be done seperately (seperate policy statements).

    Likewise, if you want to reduce the consideration set such that we only
    compare certain keys (e.g. you only want to compare the `Protocol-` keys),
    you can use the `matching` option with a regular expression:

    :example:

    .. code-block:: yaml

            policies:
              - name: elb-ssl-policies
                resource: elb
                filters:
                  - type: ssl-policy
                    blacklist:
                        - "Protocol-SSLv2"
                        - "Protocol-SSLv3"
              - name: elb-modern-tls
                resource: elb
                filters:
                  - type: ssl-policy
                    matching: "^Protocol-"
                    whitelist:
                        - "Protocol-TLSv1.1"
                        - "Protocol-TLSv1.2"
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
            'matching': {'type': 'string'},
            'whitelist': {'type': 'array', 'items': {'type': 'string'}},
            'blacklist': {'type': 'array', 'items': {'type': 'string'}}
        }
    }
    permissions = ("elasticloadbalancing:DescribeLoadBalancerPolicies",)

    def validate(self):
        if 'whitelist' in self.data and 'blacklist' in self.data:
            raise PolicyValidationError(
                "cannot specify whitelist and black list on %s" % (
                    self.manager.data,))
        if 'whitelist' not in self.data and 'blacklist' not in self.data:
            raise PolicyValidationError(
                "must specify either policy blacklist or whitelist on %s" % (
                    self.manager.data,))
        if ('blacklist' in self.data and
                not isinstance(self.data['blacklist'], list)):
            raise PolicyValidationError("blacklist must be a list on %s" % (
                self.manager.data,))

        if 'matching' in self.data:
                # Sanity check that we can compile
                try:
                    re.compile(self.data['matching'])
                except re.error as e:
                    raise PolicyValidationError(
                        "Invalid regex: %s %s" % (e, self.manager.data))

        return self

    def process(self, balancers, event=None):
        balancers = [b for b in balancers if is_ssl(b)]
        active_policy_attribute_tuples = (
            self.create_elb_active_policy_attribute_tuples(balancers))

        whitelist = set(self.data.get('whitelist', []))
        blacklist = set(self.data.get('blacklist', []))

        invalid_elbs = []

        if 'matching' in self.data:
            regex = self.data.get('matching')
            filtered_pairs = []
            for (elb, active_policies) in active_policy_attribute_tuples:
                filtered_policies = [policy for policy in active_policies if
                bool(re.match(regex, policy, flags=re.IGNORECASE))]
                if filtered_policies:
                    filtered_pairs.append((elb, filtered_policies))
            active_policy_attribute_tuples = filtered_pairs

        if blacklist:
            for elb, active_policies in active_policy_attribute_tuples:
                if len(blacklist.intersection(active_policies)) > 0:
                    elb["ProhibitedPolicies"] = list(
                        blacklist.intersection(active_policies))
                    invalid_elbs.append(elb)
        elif whitelist:
            for elb, active_policies in active_policy_attribute_tuples:
                if len(set(active_policies).difference(whitelist)) > 0:
                    elb["ProhibitedPolicies"] = list(
                        set(active_policies).difference(whitelist))
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
        with self.executor_factory(max_workers=2) as w:
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

    @worker
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
            ssl_policies = []
            for p in policies:
                if p['PolicyTypeName'] != 'SSLNegotiationPolicyType':
                    continue
                ssl_policies.append(p['PolicyName'])
                active_lb_policies.extend(
                    [policy_description['AttributeName']
                     for policy_description in
                     p['PolicyAttributeDescriptions']
                     if policy_description['AttributeValue'] == 'true']
                )
            elb['c7n.ssl-policies'] = ssl_policies
            results.append((elb, active_lb_policies))

        return results


@filters.register('healthcheck-protocol-mismatch')
class HealthCheckProtocolMismatch(Filter):
    """Filters ELB that have a healtch check protocol mismatch

    The mismatch occurs if the ELB has a different protocol to check than
    the associated instances allow to determine health status.

    :example:

    .. code-block:: yaml

            policies:
              - name: elb-healthcheck-mismatch
                resource: elb
                filters:
                  - type: healthcheck-protocol-mismatch
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

    :example:

    .. code-block:: yaml

            policies:
              - name: elb-default-vpc
                resource: elb
                filters:
                  - type: default-vpc
    """

    schema = type_schema('default-vpc')

    def __call__(self, elb):
        return elb.get('VPCId') and self.match(elb.get('VPCId')) or False


class ELBAttributeFilterBase(object):
    """ Mixin base class for filters that query LB attributes.
    """

    def initialize(self, elbs):
        def _process_attributes(elb):
            if 'Attributes' not in elb:
                client = local_session(
                    self.manager.session_factory).client('elb')
                results = client.describe_load_balancer_attributes(
                    LoadBalancerName=elb['LoadBalancerName'])
                elb['Attributes'] = results['LoadBalancerAttributes']

        with self.manager.executor_factory(max_workers=2) as w:
            list(w.map(_process_attributes, elbs))


@filters.register('is-logging')
class IsLoggingFilter(Filter, ELBAttributeFilterBase):
    """Matches ELBs that are logging to S3.
        bucket and prefix are optional

    :example:

    .. code-block:: yaml

            policies:
            - name: elb-is-logging-test
              resource: elb
              filters:
                - type: is-logging

            - name: elb-is-logging-bucket-and-prefix-test
              resource: elb
              filters:
                - type: is-logging
                  bucket: prodlogs
                  prefix: elblogs
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

        return [elb for elb in resources
                if elb['Attributes']['AccessLog']['Enabled'] and
                (not bucket_name or bucket_name == elb['Attributes'][
                    'AccessLog'].get('S3BucketName', None)) and
                (not bucket_prefix or bucket_prefix == elb['Attributes'][
                    'AccessLog'].get('S3BucketPrefix', None))
                ]


@filters.register('is-not-logging')
class IsNotLoggingFilter(Filter, ELBAttributeFilterBase):
    """ Matches ELBs that are NOT logging to S3.
        or do not match the optional bucket and/or prefix.

    :example:

    .. code-block:: yaml

            policies:
                - name: elb-is-not-logging-test
                  resource: elb
                  filters:
                    - type: is-not-logging

                - name: is-not-logging-bucket-and-prefix-test
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

        return [elb for elb in resources
                if not elb['Attributes']['AccessLog']['Enabled'] or
                (bucket_name and bucket_name != elb['Attributes'][
                    'AccessLog'].get(
                    'S3BucketName', None)) or
                (bucket_prefix and bucket_prefix != elb['Attributes'][
                    'AccessLog'].get(
                    'S3BucketPrefix', None))
                ]
