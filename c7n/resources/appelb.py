# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Application & Network Load Balancers
"""
import json
import logging

from collections import defaultdict
from c7n.actions import ActionRegistry, BaseAction, ModifyVpcSecurityGroupsAction
from c7n.exceptions import PolicyValidationError
from c7n.filters import (
    Filter, FilterRegistry, DefaultVpcBase, MetricsFilter, ValueFilter)
import c7n.filters.vpc as net_filters
from c7n import tags
from c7n.manager import resources

from c7n.query import QueryResourceManager, DescribeSource, ConfigSource, TypeInfo
from c7n.utils import (
    local_session, chunks, type_schema, get_retry, set_annotation)

from c7n.resources.aws import Arn
from c7n.resources.shield import IsShieldProtected, SetShieldProtection

log = logging.getLogger('custodian.app-elb')


class DescribeAppElb(DescribeSource):

    def get_resources(self, ids, cache=True):
        """Support server side filtering on arns or names
        """
        if ids[0].startswith('arn:'):
            params = {'LoadBalancerArns': ids}
        else:
            params = {'Names': ids}
        return self.query.filter(self.manager, **params)

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
        item_attrs = item['supplementaryConfiguration'][
            'LoadBalancerAttributes']
        if isinstance(item_attrs, str):
            item_attrs = json.loads(item_attrs)
        # Matches annotation of AppELBAttributeFilterBase filter
        resource['Attributes'] = {
            attr['key']: parse_attribute_value(attr['value']) for
            attr in item_attrs}
        return resource


@resources.register('app-elb')
class AppELB(QueryResourceManager):
    """Resource manager for v2 ELBs (AKA ALBs and NLBs).
    """

    class resource_type(TypeInfo):
        service = 'elbv2'
        permission_prefix = 'elasticloadbalancing'
        enum_spec = ('describe_load_balancers', 'LoadBalancers', None)
        name = 'LoadBalancerName'
        id = 'LoadBalancerArn'
        filter_name = "Names"
        filter_type = "list"
        dimension = "LoadBalancer"
        date = 'CreatedTime'
        cfn_type = config_type = 'AWS::ElasticLoadBalancingV2::LoadBalancer'
        arn = "LoadBalancerArn"
        # The suffix varies by type of loadbalancer (app vs net)
        arn_type = 'loadbalancer/app'

    retry = staticmethod(get_retry(('Throttling',)))
    source_mapping = {
        'describe': DescribeAppElb,
        'config': ConfigAppElb
    }

    @classmethod
    def get_permissions(cls):
        # override as the service is not the iam prefix
        return ("elasticloadbalancing:DescribeLoadBalancers",
                "elasticloadbalancing:DescribeLoadBalancerAttributes",
                "elasticloadbalancing:DescribeTags")


def _describe_appelb_tags(albs, session_factory, executor_factory, retry):
    client = local_session(session_factory).client('elbv2')

    def _process_tags(alb_set):
        alb_map = {alb['LoadBalancerArn']: alb for alb in alb_set}

        results = retry(client.describe_tags, ResourceArns=list(alb_map.keys()))
        for tag_desc in results['TagDescriptions']:
            if ('ResourceArn' in tag_desc and
                    tag_desc['ResourceArn'] in alb_map):
                alb_map[tag_desc['ResourceArn']]['Tags'] = tag_desc['Tags']

    with executor_factory(max_workers=2) as w:
        list(w.map(_process_tags, chunks(albs, 20)))


AppELB.filter_registry.register('tag-count', tags.TagCountFilter)
AppELB.filter_registry.register('marked-for-op', tags.TagActionFilter)
AppELB.filter_registry.register('shield-enabled', IsShieldProtected)
AppELB.filter_registry.register('network-location', net_filters.NetworkLocation)
AppELB.action_registry.register('set-shield', SetShieldProtection)


@AppELB.filter_registry.register('metrics')
class AppElbMetrics(MetricsFilter):
    """Filter app/net load balancer by metric values.

    Note application and network load balancers use different Cloud
    Watch metrics namespaces and metric names, the custodian app-elb
    resource returns both types of load balancer, so an additional
    filter should be used to ensure only targeting a particular
    type. ie.  `- Type: application` or `- Type: network`

    See available application load balancer metrics here
    https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html

    See available network load balancer metrics here.
    https://docs.aws.amazon.com/elasticloadbalancing/latest/network/load-balancer-cloudwatch-metrics.html


    For network load balancer metrics, the metrics filter requires specifying
    the namespace parameter to the filter.

    .. code-block:: yaml

      policies:
        - name: net-lb-underutilized
          resource: app-elb
          filters:
           - Type: network
           - type: metrics
             name: ActiveFlowCount
             namespace: AWS/NetworkELB
             statistics: Sum
             days: 14
             value: 100
             op: less-than
    """

    def get_dimensions(self, resource):
        return [{
            'Name': self.model.dimension,
            'Value': Arn.parse(resource['LoadBalancerArn']).resource}]


@AppELB.filter_registry.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[]"


@AppELB.filter_registry.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "AvailabilityZones[].SubnetId"


@AppELB.filter_registry.register('vpc')
class VpcFilter(net_filters.VpcFilter):

    RelatedIdsExpression = "VpcId"


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

        wafs = self.manager.get_resource_manager('waf-regional').resources(augment=False)

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
        if target_acl and target_acl_id not in name_id_map.values():
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
        for f in self.manager.iter_filters():
            if isinstance(f, WafEnabled):
                found = True
                break
        if not found:
            # try to ensure idempotent usage
            raise PolicyValidationError(
                "set-waf should be used in conjunction with waf-enabled filter on %s" % (
                    self.manager.data,))
        return self

    def process(self, resources):
        wafs = self.manager.get_resource_manager('waf-regional').resources(augment=False)
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


@AppELB.action_registry.register('set-s3-logging')
class SetS3Logging(BaseAction):
    """Action to enable/disable S3 logging for an application loadbalancer.

    :example:

    .. code-block:: yaml

            policies:
              - name: elbv2-test
                resource: app-elb
                filters:
                  - type: is-not-logging
                actions:
                  - type: set-s3-logging
                    bucket: elbv2logtest
                    prefix: dahlogs
                    state: enabled
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
                raise PolicyValidationError((
                    "alb logging enablement requires `bucket` "
                    "and `prefix` specification on %s" % (self.manager.data,)))
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


@AppELB.action_registry.register('mark-for-op')
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


@AppELB.action_registry.register('tag')
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

    def process_resource_set(self, client, resource_set, ts):
        client.add_tags(
            ResourceArns=[alb['LoadBalancerArn'] for alb in resource_set],
            Tags=ts)


@AppELB.action_registry.register('remove-tag')
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

    def process_resource_set(self, client, resource_set, tag_keys):
        client.remove_tags(
            ResourceArns=[alb['LoadBalancerArn'] for alb in resource_set],
            TagKeys=tag_keys)


@AppELB.action_registry.register('delete')
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
        client = local_session(self.manager.session_factory).client('elbv2')
        for lb in load_balancers:
            self.process_alb(client, lb)

    def process_alb(self, client, alb):
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
        except client.exceptions.LoadBalancerNotFoundException:
            pass
        except client.exceptions.OperationNotPermittedException as e:
            self.log.warning(
                "Exception trying to delete ALB: %s error: %s",
                alb['LoadBalancerArn'], e)


class AppELBListenerFilterBase:
    """ Mixin base class for filters that query LB listeners.
    """
    permissions = ("elasticloadbalancing:DescribeListeners",)

    def initialize(self, albs):
        client = local_session(self.manager.session_factory).client('elbv2')
        self.listener_map = defaultdict(list)
        for alb in albs:
            try:
                results = client.describe_listeners(
                    LoadBalancerArn=alb['LoadBalancerArn'])
            except client.exceptions.LoadBalancerNotFoundException:
                continue
            self.listener_map[alb['LoadBalancerArn']] = results['Listeners']


def parse_attribute_value(v):
    if v.isdigit():
        v = int(v)
    elif v == 'true':
        v = True
    elif v == 'false':
        v = False
    return v


class AppELBAttributeFilterBase:
    """ Mixin base class for filters that query LB attributes.
    """

    def initialize(self, albs):
        client = local_session(self.manager.session_factory).client('elbv2')

        def _process_attributes(alb):
            if 'Attributes' not in alb:
                alb['Attributes'] = {}
                results = client.describe_load_balancer_attributes(
                    LoadBalancerArn=alb['LoadBalancerArn'])
                # flatten out the list of dicts and cast
                for pair in results['Attributes']:
                    k = pair['Key']
                    v = parse_attribute_value(pair['Value'])
                    alb['Attributes'][k] = v

        with self.manager.executor_factory(max_workers=2) as w:
            list(w.map(_process_attributes, albs))


@AppELB.filter_registry.register('is-logging')
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


@AppELB.filter_registry.register('is-not-logging')
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
                    'access_logs.s3.prefix', None))]


@AppELB.filter_registry.register('attributes')
class CheckAttributes(ValueFilter, AppELBAttributeFilterBase):
    """ Value filter that allows filtering on ELBv2 attributes

    :example:

    .. code-block:: yaml

            policies:
                - name: alb-http2-enabled
                  resource: app-elb
                  filters:
                    - type: attributes
                      key: routing.http2.enabled
                      value: true
                      op: eq
    """
    annotate: False  # no annotation from value Filter
    permissions = ("elasticloadbalancing:DescribeLoadBalancerAttributes",)
    schema = type_schema('attributes', rinherit=ValueFilter.schema)
    schema_alias = False

    def process(self, resources, event=None):
        self.augment(resources)
        return super().process(resources, event)

    def augment(self, resources):
        self.initialize(resources)

    def __call__(self, r):
        return super().__call__(r['Attributes'])


class AppELBTargetGroupFilterBase:
    """ Mixin base class for filters that query LB target groups.
    """

    def initialize(self, albs):
        self.target_group_map = defaultdict(list)
        target_groups = self.manager.get_resource_manager(
            'app-elb-target-group').resources()
        for target_group in target_groups:
            for load_balancer_arn in target_group['LoadBalancerArns']:
                self.target_group_map[load_balancer_arn].append(target_group)


@AppELB.filter_registry.register('listener')
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
    schema_alias = False
    permissions = ("elasticloadbalancing:DescribeLoadBalancerAttributes",)

    def validate(self):
        if not self.data.get('matched'):
            return
        listeners = list(self.manager.iter_filters())
        found = False
        for f in listeners[:listeners.index(self)]:
            if not f.data.get('matched', False):
                found = True
                break
        if not found:
            raise PolicyValidationError(
                "matched listener filter, requires preceding listener filter on %s " % (
                    self.manager.data,))
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


@AppELB.action_registry.register('modify-listener')
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
        for f in self.manager.iter_filters():
            if f.type == 'listener':
                return self
        raise PolicyValidationError(
            "modify-listener action requires the listener filter %s" % (
                self.manager.data,))

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
        client = local_session(self.manager.session_factory).client('elbv2')

        for alb in load_balancers:
            for matched_listener in alb.get('c7n:MatchedListeners', ()):
                client.modify_listener(
                    ListenerArn=matched_listener['ListenerArn'],
                    **args)


@AppELB.action_registry.register('modify-security-groups')
class AppELBModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):

    permissions = ("elasticloadbalancing:SetSecurityGroups",)

    def process(self, albs):
        client = local_session(self.manager.session_factory).client('elbv2')
        groups = super(AppELBModifyVpcSecurityGroups, self).get_groups(albs)

        for idx, i in enumerate(albs):
            try:
                client.set_security_groups(
                    LoadBalancerArn=i['LoadBalancerArn'],
                    SecurityGroups=groups[idx])
            except client.exceptions.LoadBalancerNotFoundException:
                continue


@AppELB.filter_registry.register('healthcheck-protocol-mismatch')
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


@AppELB.filter_registry.register('target-group')
class AppELBTargetGroupFilter(ValueFilter, AppELBTargetGroupFilterBase):
    """Filter ALB based on matching target group value"""

    schema = type_schema('target-group', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ("elasticloadbalancing:DescribeTargetGroups",)

    def process(self, albs, event=None):
        self.initialize(albs)
        return super(AppELBTargetGroupFilter, self).process(albs, event)

    def __call__(self, alb):
        target_groups = self.target_group_map[alb['LoadBalancerArn']]
        return self.match(target_groups)


@AppELB.filter_registry.register('default-vpc')
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

    class resource_type(TypeInfo):
        service = 'elbv2'
        arn_type = 'target-group'
        enum_spec = ('describe_target_groups', 'TargetGroups', None)
        name = 'TargetGroupName'
        id = 'TargetGroupArn'
        permission_prefix = 'elasticloadbalancing'
        cfn_type = 'AWS::ElasticLoadBalancingV2::TargetGroup'

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
        client = local_session(self.session_factory).client('elbv2')

        def _describe_target_group_health(target_group):
            result = self.retry(client.describe_target_health,
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
    client = local_session(session_factory).client('elbv2')

    def _process_tags(target_group_set):
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


@AppELBTargetGroup.action_registry.register('mark-for-op')
class AppELBTargetGroupMarkForOpAction(tags.TagDelayedAction):
    """Action to specify a delayed action on an ELB target group"""


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

    def process_resource_set(self, client, resource_set, ts):
        client.add_tags(
            ResourceArns=[tgroup['TargetGroupArn'] for tgroup in resource_set],
            Tags=ts)


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

    def process_resource_set(self, client, resource_set, tag_keys):
        client.remove_tags(
            ResourceArns=[tgroup['TargetGroupArn'] for tgroup in resource_set],
            TagKeys=tag_keys)


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

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('elbv2')
        for tg in resources:
            self.process_target_group(client, tg)

    def process_target_group(self, client, target_group):
        self.manager.retry(
            client.delete_target_group,
            TargetGroupArn=target_group['TargetGroupArn'])
