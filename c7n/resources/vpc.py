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

import itertools
import operator
import zlib
import functools
import jmespath

from botocore.exceptions import ClientError as BotoClientError

from c7n.actions import BaseAction, ModifyVpcSecurityGroupsAction
from c7n.exceptions import PolicyValidationError
from c7n.filters import (
    DefaultVpcBase, Filter, ValueFilter)
import c7n.filters.vpc as net_filters
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.filters.related import RelatedResourceFilter
from c7n.filters.revisions import Diff
from c7n.filters.locked import Locked
from c7n import query, resolver
from c7n.manager import resources
from c7n.utils import (
    chunks, local_session, type_schema, get_retry, parse_cidr, generate_arn)
from botocore.exceptions import ClientError
from c7n.resources.shield import IsShieldProtected, SetShieldProtection


@resources.register('vpc')
class Vpc(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'vpc'
        enum_spec = ('describe_vpcs', 'Vpcs', None)
        name = id = 'VpcId'
        filter_name = 'VpcIds'
        filter_type = 'list'
        date = None
        dimension = None
        config_type = 'AWS::EC2::VPC'
        id_prefix = "vpc-"


@Vpc.filter_registry.register('flow-logs')
class FlowLogFilter(Filter):
    """Are flow logs enabled on the resource.

    ie to find all vpcs with flows logs disabled we can do this

    :example:

    .. code-block:: yaml

            policies:
              - name: flow-logs-enabled
                resource: vpc
                filters:
                  - flow-logs

    or to find all vpcs with flow logs but that don't match a
    particular configuration.

    :example:

    .. code-block:: yaml

            policies:
              - name: flow-mis-configured
                resource: vpc
                filters:
                  - not:
                    - type: flow-logs
                      enabled: true
                      set-op: or
                      op: equal
                      # equality operator applies to following keys
                      traffic-type: all
                      status: active
                      log-group: vpc-logs

    """

    schema = type_schema(
        'flow-logs',
        **{'enabled': {'type': 'boolean', 'default': False},
           'op': {'enum': ['equal', 'not-equal'], 'default': 'equal'},
           'set-op': {'enum': ['or', 'and'], 'default': 'or'},
           'status': {'enum': ['active']},
           'traffic-type': {'enum': ['accept', 'reject', 'all']},
           'log-group': {'type': 'string'}})

    permissions = ('ec2:DescribeFlowLogs',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ec2')

        # TODO given subnet/nic level logs, we should paginate, but we'll
        # need to add/update botocore pagination support.
        logs = client.describe_flow_logs().get('FlowLogs', ())

        m = self.manager.get_model()
        resource_map = {}

        for fl in logs:
            resource_map.setdefault(fl['ResourceId'], []).append(fl)

        enabled = self.data.get('enabled', False)
        log_group = self.data.get('log-group')
        traffic_type = self.data.get('traffic-type')
        status = self.data.get('status')
        op = self.data.get('op', 'equal') == 'equal' and operator.eq or operator.ne
        set_op = self.data.get('set-op', 'or')

        results = []
        # looping over vpc resources
        for r in resources:

            if r[m.id] not in resource_map:
                # we didn't find a flow log for this vpc
                if enabled:
                    # vpc flow logs not enabled so exclude this vpc from results
                    continue
                results.append(r)
                continue
            flogs = resource_map[r[m.id]]
            r['c7n:flow-logs'] = flogs

            # config comparisons are pointless if we only want vpcs with no flow logs
            if enabled:
                fl_matches = []
                for fl in flogs:
                    status_match = (status is None) or op(fl['FlowLogStatus'], status.upper())
                    traffic_type_match = (
                        traffic_type is None) or op(
                        fl['TrafficType'],
                        traffic_type.upper())
                    log_group_match = (log_group is None) or op(fl['LogGroupName'], log_group)

                    # combine all conditions to check if flow log matches the spec
                    fl_match = status_match and traffic_type_match and log_group_match
                    fl_matches.append(fl_match)

                if set_op == 'or':
                    if any(fl_matches):
                        results.append(r)
                elif set_op == 'and':
                    if all(fl_matches):
                        results.append(r)

        return results


@Vpc.filter_registry.register('security-group')
class VpcSecurityGroupFilter(RelatedResourceFilter):
    """Filter VPCs based on Security Group attributes

    :example:

    .. code-block:: yaml

            policies:
              - name: gray-vpcs
                resource: vpc
                filters:
                  - type: security-group
                    key: tag:Color
                    value: Gray
    """
    schema = type_schema(
        'security-group', rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})
    RelatedResource = "c7n.resources.vpc.SecurityGroup"
    RelatedIdsExpression = '[SecurityGroups][].GroupId'
    AnnotationKey = "matched-vpcs"

    def get_related_ids(self, resources):
        vpc_ids = [vpc['VpcId'] for vpc in resources]
        vpc_group_ids = {
            g['GroupId'] for g in
            self.manager.get_resource_manager('security-group').resources()
            if g.get('VpcId', '') in vpc_ids
        }
        return vpc_group_ids


@Vpc.filter_registry.register('vpc-attributes')
class AttributesFilter(Filter):
    """Filters VPCs based on their DNS attributes

    :example:

    .. code-block:: yaml

            policies:
              - name: dns-hostname-enabled
                resource: vpc
                filters:
                  - type: vpc-attributes
                    dnshostnames: True
    """
    schema = type_schema(
        'vpc-attributes',
        dnshostnames={'type': 'boolean'},
        dnssupport={'type': 'boolean'})
    permissions = ('ec2:DescribeVpcAttributes',)

    def process(self, resources, event=None):
        results = []
        client = local_session(self.manager.session_factory).client('ec2')
        dns_hostname = self.data.get('dnshostnames', None)
        dns_support = self.data.get('dnssupport', None)

        for r in resources:
            if dns_hostname is not None:
                hostname = client.describe_vpc_attribute(
                    VpcId=r['VpcId'],
                    Attribute='enableDnsHostnames'
                )['EnableDnsHostnames']['Value']
            if dns_support is not None:
                support = client.describe_vpc_attribute(
                    VpcId=r['VpcId'],
                    Attribute='enableDnsSupport'
                )['EnableDnsSupport']['Value']
            if dns_hostname is not None and dns_support is not None:
                if dns_hostname == hostname and dns_support == support:
                    results.append(r)
            elif dns_hostname is not None and dns_support is None:
                if dns_hostname == hostname:
                    results.append(r)
            elif dns_support is not None and dns_hostname is None:
                if dns_support == support:
                    results.append(r)
        return results


@Vpc.filter_registry.register('dhcp-options')
class DhcpOptionsFilter(Filter):
    """Filter VPCs based on their dhcp options

     :example:

     .. code-block: yaml

        - policies:
             - name: vpcs-in-domain
               resource: vpc
               filters:
                 - type: dhcp-options
                   domain-name: ec2.internal

    if an option value is specified as a list, then all elements must be present.
    if an option value is specified as a string, then that string must be present.

    vpcs not matching a given option value can be found via specifying
    a `present: false` parameter.

    """

    option_keys = ('domain-name', 'domain-name-servers', 'ntp-servers')
    schema = type_schema('dhcp-options', **{
        k: {'oneOf': [
            {'type': 'array', 'items': {'type': 'string'}},
            {'type': 'string'}]}
        for k in option_keys})
    schema['properties']['present'] = {'type': 'boolean'}
    permissions = ('ec2:DescribeDhcpOptions',)

    def validate(self):
        if not any([self.data.get(k) for k in self.option_keys]):
            raise PolicyValidationError("one of %s required" % (self.option_keys,))
        return self

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ec2')
        option_ids = [r['DhcpOptionsId'] for r in resources]
        options_map = {}
        results = []
        for options in client.describe_dhcp_options(
                Filters=[{
                    'Name': 'dhcp-options-id',
                    'Values': option_ids}]).get('DhcpOptions', ()):
            options_map[options['DhcpOptionsId']] = {
                o['Key']: [v['Value'] for v in o['Values']]
                for o in options['DhcpConfigurations']}

        for vpc in resources:
            if self.process_vpc(vpc, options_map[vpc['DhcpOptionsId']]):
                results.append(vpc)
        return results

    def process_vpc(self, vpc, dhcp):
        vpc['c7n:DhcpConfiguration'] = dhcp
        found = True
        for k in self.option_keys:
            if k not in self.data:
                continue
            is_list = isinstance(self.data[k], list)
            if k not in dhcp:
                found = False
            elif not is_list and self.data[k] not in dhcp[k]:
                found = False
            elif is_list and sorted(self.data[k]) != sorted(dhcp[k]):
                found = False
        if not self.data.get('present', True):
            found = not found
        return found


@resources.register('subnet')
class Subnet(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'subnet'
        enum_spec = ('describe_subnets', 'Subnets', None)
        name = id = 'SubnetId'
        filter_name = 'SubnetIds'
        filter_type = 'list'
        date = None
        dimension = None
        config_type = 'AWS::EC2::Subnet'
        id_prefix = "subnet-"


Subnet.filter_registry.register('flow-logs', FlowLogFilter)


@resources.register('security-group')
class SecurityGroup(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'security-group'
        enum_spec = ('describe_security_groups', 'SecurityGroups', None)
        detail_spec = None
        name = id = 'GroupId'
        filter_name = "GroupIds"
        filter_type = 'list'
        date = None
        dimension = None
        config_type = "AWS::EC2::SecurityGroup"
        id_prefix = "sg-"

    def get_source(self, source_type):
        if source_type == 'config':
            return ConfigSG(self)
        return super(SecurityGroup, self).get_source(source_type)


class ConfigSG(query.ConfigSource):

    def load_resource(self, item):
        r = super(ConfigSG, self).load_resource(item)
        for rset in ('IpPermissions', 'IpPermissionsEgress'):
            for p in r.get(rset, ()):
                if p.get('FromPort', '') is None:
                    p.pop('FromPort')
                if p.get('ToPort', '') is None:
                    p.pop('ToPort')
                if 'Ipv6Ranges' not in p:
                    p[u'Ipv6Ranges'] = []
                for i in p.get('UserIdGroupPairs', ()):
                    for k, v in list(i.items()):
                        if v is None:
                            i.pop(k)
                # legacy config form, still version 1.2
                for attribute, element_key in (('IpRanges', u'CidrIp'),):
                    if attribute not in p:
                        continue
                    p[attribute] = [{element_key: v} for v in p[attribute]]
                if 'Ipv4Ranges' in p:
                    p['IpRanges'] = p.pop('Ipv4Ranges')
        return r


@SecurityGroup.filter_registry.register('locked')
class SecurityGroupLockedFilter(Locked):

    def get_parent_id(self, resource, account_id):
        return resource.get('VpcId', account_id)


@SecurityGroup.filter_registry.register('diff')
class SecurityGroupDiffFilter(Diff):

    def diff(self, source, target):
        differ = SecurityGroupDiff()
        return differ.diff(source, target)


class SecurityGroupDiff(object):
    """Diff two versions of a security group

    Immutable: GroupId, GroupName, Description, VpcId, OwnerId
    Mutable: Tags, Rules
    """

    def diff(self, source, target):
        delta = {}
        tag_delta = self.get_tag_delta(source, target)
        if tag_delta:
            delta['tags'] = tag_delta
        ingress_delta = self.get_rule_delta('IpPermissions', source, target)
        if ingress_delta:
            delta['ingress'] = ingress_delta
        egress_delta = self.get_rule_delta(
            'IpPermissionsEgress', source, target)
        if egress_delta:
            delta['egress'] = egress_delta
        if delta:
            return delta

    def get_tag_delta(self, source, target):
        source_tags = {t['Key']: t['Value'] for t in source.get('Tags', ())}
        target_tags = {t['Key']: t['Value'] for t in target.get('Tags', ())}
        target_keys = set(target_tags.keys())
        source_keys = set(source_tags.keys())
        removed = source_keys.difference(target_keys)
        added = target_keys.difference(source_keys)
        changed = set()
        for k in target_keys.intersection(source_keys):
            if source_tags[k] != target_tags[k]:
                changed.add(k)
        return {k: v for k, v in {
            'added': {k: target_tags[k] for k in added},
            'removed': {k: source_tags[k] for k in removed},
            'updated': {k: target_tags[k] for k in changed}}.items() if v}

    def get_rule_delta(self, key, source, target):
        source_rules = {
            self.compute_rule_hash(r): r for r in source.get(key, ())}
        target_rules = {
            self.compute_rule_hash(r): r for r in target.get(key, ())}
        source_keys = set(source_rules.keys())
        target_keys = set(target_rules.keys())
        removed = source_keys.difference(target_keys)
        added = target_keys.difference(source_keys)
        return {k: v for k, v in
                {'removed': [source_rules[rid] for rid in sorted(removed)],
                 'added': [target_rules[rid] for rid in sorted(added)]}.items() if v}

    RULE_ATTRS = (
        ('PrefixListIds', 'PrefixListId'),
        ('UserIdGroupPairs', 'GroupId'),
        ('IpRanges', 'CidrIp'),
        ('Ipv6Ranges', 'CidrIpv6')
    )

    def compute_rule_hash(self, rule):
        buf = "%d-%d-%s-" % (
            rule.get('FromPort', 0) or 0,
            rule.get('ToPort', 0) or 0,
            rule.get('IpProtocol', '-1') or '-1'
        )
        for a, ke in self.RULE_ATTRS:
            if a not in rule:
                continue
            ev = [e[ke] for e in rule[a]]
            ev.sort()
            for e in ev:
                buf += "%s-" % e
        # mask to generate the same numeric value across all Python versions
        return zlib.crc32(buf.encode('ascii')) & 0xffffffff


@SecurityGroup.action_registry.register('patch')
class SecurityGroupApplyPatch(BaseAction):
    """Modify a resource via application of a reverse delta.
    """
    schema = type_schema('patch')

    permissions = ('ec2:AuthorizeSecurityGroupIngress',
                   'ec2:AuthorizeSecurityGroupEgress',
                   'ec2:RevokeSecurityGroupIngress',
                   'ec2:RevokeSecurityGroupEgress',
                   'ec2:CreateTags',
                   'ec2:DeleteTags')

    def validate(self):
        diff_filters = [n for n in self.manager.filters if isinstance(
            n, SecurityGroupDiffFilter)]
        if not len(diff_filters):
            raise PolicyValidationError(
                "resource patching requires diff filter")
        return self

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        differ = SecurityGroupDiff()
        patcher = SecurityGroupPatch()
        for r in resources:
            # reverse the patch by computing fresh, the forward
            # patch is for notifications
            d = differ.diff(r, r['c7n:previous-revision']['resource'])
            patcher.apply_delta(client, r, d)


class SecurityGroupPatch(object):

    RULE_TYPE_MAP = {
        'egress': ('IpPermissionsEgress',
                   'revoke_security_group_egress',
                   'authorize_security_group_egress'),
        'ingress': ('IpPermissions',
                    'revoke_security_group_ingress',
                    'authorize_security_group_ingress')}

    retry = staticmethod(get_retry((
        'RequestLimitExceeded', 'Client.RequestLimitExceeded')))

    def apply_delta(self, client, target, change_set):
        if 'tags' in change_set:
            self.process_tags(client, target, change_set['tags'])
        if 'ingress' in change_set:
            self.process_rules(
                client, 'ingress', target, change_set['ingress'])
        if 'egress' in change_set:
            self.process_rules(
                client, 'egress', target, change_set['egress'])

    def process_tags(self, client, group, tag_delta):
        if 'removed' in tag_delta:
            self.retry(client.delete_tags,
                       Resources=[group['GroupId']],
                       Tags=[{'Key': k}
                             for k in tag_delta['removed']])
        tags = []
        if 'added' in tag_delta:
            tags.extend(
                [{'Key': k, 'Value': v}
                 for k, v in tag_delta['added'].items()])
        if 'updated' in tag_delta:
            tags.extend(
                [{'Key': k, 'Value': v}
                 for k, v in tag_delta['updated'].items()])
        if tags:
            self.retry(
                client.create_tags, Resources=[group['GroupId']], Tags=tags)

    def process_rules(self, client, rule_type, group, delta):
        key, revoke_op, auth_op = self.RULE_TYPE_MAP[rule_type]
        revoke, authorize = getattr(
            client, revoke_op), getattr(client, auth_op)

        # Process removes
        if 'removed' in delta:
            self.retry(revoke, GroupId=group['GroupId'],
                       IpPermissions=[r for r in delta['removed']])

        # Process adds
        if 'added' in delta:
            self.retry(authorize, GroupId=group['GroupId'],
                       IpPermissions=[r for r in delta['added']])


class SGUsage(Filter):

    def get_permissions(self):
        return list(itertools.chain(
            [self.manager.get_resource_manager(m).get_permissions()
             for m in
             ['lambda', 'eni', 'launch-config', 'security-group']]))

    def filter_peered_refs(self, resources):
        if not resources:
            return resources
        # Check that groups are not referenced across accounts
        client = local_session(self.manager.session_factory).client('ec2')
        peered_ids = set()
        for resource_set in chunks(resources, 200):
            for sg_ref in client.describe_security_group_references(
                    GroupId=[r['GroupId'] for r in resource_set]
            )['SecurityGroupReferenceSet']:
                peered_ids.add(sg_ref['GroupId'])
        self.log.debug(
            "%d of %d groups w/ peered refs", len(peered_ids), len(resources))
        return [r for r in resources if r['GroupId'] not in peered_ids]

    def scan_groups(self):
        used = set()
        for kind, scanner in (
                ("nics", self.get_eni_sgs),
                ("sg-perm-refs", self.get_sg_refs),
                ('lambdas', self.get_lambda_sgs),
                ("launch-configs", self.get_launch_config_sgs),
        ):
            sg_ids = scanner()
            new_refs = sg_ids.difference(used)
            used = used.union(sg_ids)
            self.log.debug(
                "%s using %d sgs, new refs %s total %s",
                kind, len(sg_ids), len(new_refs), len(used))

        return used

    def get_launch_config_sgs(self):
        # Note assuming we also have launch config garbage collection
        # enabled.
        sg_ids = set()
        for cfg in self.manager.get_resource_manager('launch-config').resources():
            for g in cfg['SecurityGroups']:
                sg_ids.add(g)
            for g in cfg['ClassicLinkVPCSecurityGroups']:
                sg_ids.add(g)
        return sg_ids

    def get_lambda_sgs(self):
        sg_ids = set()
        for func in self.manager.get_resource_manager('lambda').resources():
            if 'VpcConfig' not in func:
                continue
            for g in func['VpcConfig']['SecurityGroupIds']:
                sg_ids.add(g)
        return sg_ids

    def get_eni_sgs(self):
        sg_ids = set()
        for nic in self.manager.get_resource_manager('eni').resources():
            for g in nic['Groups']:
                sg_ids.add(g['GroupId'])
        return sg_ids

    def get_sg_refs(self):
        sg_ids = set()
        for sg in self.manager.get_resource_manager('security-group').resources():
            for perm_type in ('IpPermissions', 'IpPermissionsEgress'):
                for p in sg.get(perm_type, []):
                    for g in p.get('UserIdGroupPairs', ()):
                        sg_ids.add(g['GroupId'])
        return sg_ids


@SecurityGroup.filter_registry.register('unused')
class UnusedSecurityGroup(SGUsage):
    """Filter to just vpc security groups that are not used.

    We scan all extant enis in the vpc to get a baseline set of groups
    in use. Then augment with those referenced by launch configs, and
    lambdas as they may not have extant resources in the vpc at a
    given moment. We also find any security group with references from
    other security group either within the vpc or across peered
    connections.

    Note this filter does not support classic security groups atm.

    :example:

    .. code-block:: yaml

            policies:
              - name: security-groups-unused
                resource: security-group
                filters:
                  - unused
    """
    schema = type_schema('unused')

    def process(self, resources, event=None):
        used = self.scan_groups()
        unused = [
            r for r in resources
            if r['GroupId'] not in used and 'VpcId' in r]
        return unused and self.filter_peered_refs(unused) or []


@SecurityGroup.filter_registry.register('used')
class UsedSecurityGroup(SGUsage):
    """Filter to security groups that are used.

    This operates as a complement to the unused filter for multi-step
    workflows.

    :example:

    .. code-block:: yaml

            policies:
              - name: security-groups-in-use
                resource: security-group
                filters:
                  - used
    """
    schema = type_schema('used')

    def process(self, resources, event=None):
        used = self.scan_groups()
        unused = [
            r for r in resources
            if r['GroupId'] not in used and 'VpcId' in r]
        unused = set([g['GroupId'] for g in self.filter_peered_refs(unused)])
        return [r for r in resources if r['GroupId'] not in unused]


@SecurityGroup.filter_registry.register('stale')
class Stale(Filter):
    """Filter to find security groups that contain stale references
    to other groups that are either no longer present or traverse
    a broken vpc peering connection. Note this applies to VPC
    Security groups only and will implicitly filter security groups.

    AWS Docs - https://goo.gl/nSj7VG

    :example:

    .. code-block:: yaml

            policies:
              - name: stale-security-groups
                resource: security-group
                filters:
                  - stale
    """
    schema = type_schema('stale')
    permissions = ('ec2:DescribeStaleSecurityGroups',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ec2')
        vpc_ids = set([r['VpcId'] for r in resources if 'VpcId' in r])
        group_map = {r['GroupId']: r for r in resources}
        results = []
        self.log.debug("Querying %d vpc for stale refs", len(vpc_ids))
        stale_count = 0
        for vpc_id in vpc_ids:
            stale_groups = client.describe_stale_security_groups(
                VpcId=vpc_id).get('StaleSecurityGroupSet', ())

            stale_count += len(stale_groups)
            for s in stale_groups:
                if s['GroupId'] in group_map:
                    r = group_map[s['GroupId']]
                    if 'StaleIpPermissions' in s:
                        r['MatchedIpPermissions'] = s['StaleIpPermissions']
                    if 'StaleIpPermissionsEgress' in s:
                        r['MatchedIpPermissionsEgress'] = s[
                            'StaleIpPermissionsEgress']
                    results.append(r)
        self.log.debug("Found %d stale security groups", stale_count)
        return results


@SecurityGroup.filter_registry.register('default-vpc')
class SGDefaultVpc(DefaultVpcBase):
    """Filter that returns any security group that exists within the default vpc

    :example:

    .. code-block:: yaml

            policies:
              - name: security-group-default-vpc
                resource: security-group
                filters:
                  - default-vpc
    """

    schema = type_schema('default-vpc')

    def __call__(self, resource, event=None):
        if 'VpcId' not in resource:
            return False
        return self.match(resource['VpcId'])


class SGPermission(Filter):
    """Filter for verifying security group ingress and egress permissions

    All attributes of a security group permission are available as
    value filters.

    If multiple attributes are specified the permission must satisfy
    all of them. Note that within an attribute match against a list value
    of a permission we default to or.

    If a group has any permissions that match all conditions, then it
    matches the filter.

    Permissions that match on the group are annotated onto the group and
    can subsequently be used by the remove-permission action.

    We have specialized handling for matching `Ports` in ingress/egress
    permission From/To range. The following example matches on ingress
    rules which allow for a range that includes all of the given ports.

    .. code-block:: yaml

      - type: ingress
        Ports: [22, 443, 80]

    As well for verifying that a rule only allows for a specific set of ports
    as in the following example. The delta between this and the previous
    example is that if the permission allows for any ports not specified here,
    then the rule will match. ie. OnlyPorts is a negative assertion match,
    it matches when a permission includes ports outside of the specified set.

    .. code-block:: yaml

      - type: ingress
        OnlyPorts: [22]

    For simplifying ipranges handling which is specified as a list on a rule
    we provide a `Cidr` key which can be used as a value type filter evaluated
    against each of the rules. If any iprange cidr match then the permission
    matches.

    .. code-block:: yaml

      - type: ingress
        IpProtocol: -1
        FromPort: 445

    We also have specialized handling for matching self-references in
    ingress/egress permissions. The following example matches on ingress
    rules which allow traffic its own same security group.

    .. code-block:: yaml

      - type: ingress
        SelfReference: True

    As well for assertions that a ingress/egress permission only matches
    a given set of ports, *note* OnlyPorts is an inverse match.

    .. code-block:: yaml

      - type: egress
        OnlyPorts: [22, 443, 80]

      - type: egress
        Cidr:
          value_type: cidr
          op: in
          value: x.y.z

    `Cidr` can match ipv4 rules and `CidrV6` can match ipv6 rules.  In
    this example we are blocking global inbound connections to SSH or
    RDP.

    .. code-block:: yaml

      - type: ingress
        Ports: [22, 3389]
        Cidr:
          values:
            - "0.0.0.0/0"
            - "::/0"
          op: in

    """

    perm_attrs = set((
        'IpProtocol', 'FromPort', 'ToPort', 'UserIdGroupPairs',
        'IpRanges', 'PrefixListIds'))
    filter_attrs = set(('Cidr', 'CidrV6', 'Ports', 'OnlyPorts', 'SelfReference'))
    attrs = perm_attrs.union(filter_attrs)
    attrs.add('match-operator')

    def validate(self):
        delta = set(self.data.keys()).difference(self.attrs)
        delta.remove('type')
        if delta:
            raise PolicyValidationError("Unknown keys %s on %s" % (
                ", ".join(delta), self.manager.data))
        return self

    def process(self, resources, event=None):
        self.vfilters = []
        fattrs = list(sorted(self.perm_attrs.intersection(self.data.keys())))
        self.ports = 'Ports' in self.data and self.data['Ports'] or ()
        self.only_ports = (
            'OnlyPorts' in self.data and self.data['OnlyPorts'] or ())
        for f in fattrs:
            fv = self.data.get(f)
            if isinstance(fv, dict):
                fv['key'] = f
            else:
                fv = {f: fv}
            vf = ValueFilter(fv)
            vf.annotate = False
            self.vfilters.append(vf)
        return super(SGPermission, self).process(resources, event)

    def process_ports(self, perm):
        found = None
        if 'FromPort' in perm and 'ToPort' in perm:
            for port in self.ports:
                if port >= perm['FromPort'] and port <= perm['ToPort']:
                    found = True
                    break
                found = False
            only_found = False
            for port in self.only_ports:
                if port == perm['FromPort'] and port == perm['ToPort']:
                    only_found = True
            if self.only_ports and not only_found:
                found = found is None or found and True or False
        return found

    def _process_cidr(self, cidr_key, cidr_type, range_type, perm):
        found = None
        ip_perms = perm.get(range_type, [])
        if not ip_perms:
            return False

        match_range = self.data[cidr_key]
        match_range['key'] = cidr_type

        vf = ValueFilter(match_range)
        vf.annotate = False

        for ip_range in ip_perms:
            found = vf(ip_range)
            if found:
                break
            else:
                found = False
        return found

    def process_cidrs(self, perm):
        found_v6 = found_v4 = None
        if 'CidrV6' in self.data:
            found_v6 = self._process_cidr('CidrV6', 'CidrIpv6', 'Ipv6Ranges', perm)
        if 'Cidr' in self.data:
            found_v4 = self._process_cidr('Cidr', 'CidrIp', 'IpRanges', perm)
        match_op = self.data.get('match-operator', 'and') == 'and' and all or any
        cidr_match = [k for k in (found_v6, found_v4) if k is not None]
        if not cidr_match:
            return None
        return match_op(cidr_match)

    def process_self_reference(self, perm, sg_id):
        found = None
        ref_match = self.data.get('SelfReference')
        if ref_match is not None:
            found = False
        if 'UserIdGroupPairs' in perm and 'SelfReference' in self.data:
            self_reference = sg_id in [p['GroupId']
                                       for p in perm['UserIdGroupPairs']]
            if ref_match is False and not self_reference:
                found = True
            if ref_match is True and self_reference:
                found = True
        return found

    def expand_permissions(self, permissions):
        """Expand each list of cidr, prefix list, user id group pair
        by port/protocol as an individual rule.

        The console ux automatically expands them out as addition/removal is
        per this expansion, the describe calls automatically group them.
        """
        for p in permissions:
            np = dict(p)
            values = {}
            for k in (u'IpRanges',
                      u'Ipv6Ranges',
                      u'PrefixListIds',
                      u'UserIdGroupPairs'):
                values[k] = np.pop(k, ())
                np[k] = []
            for k, v in values.items():
                if not v:
                    continue
                for e in v:
                    ep = dict(np)
                    ep[k] = [e]
                    yield ep

    def __call__(self, resource):
        matched = []
        sg_id = resource['GroupId']
        match_op = self.data.get('match-operator', 'and') == 'and' and all or any
        for perm in self.expand_permissions(resource[self.ip_permissions_key]):
            perm_matches = {}
            for idx, f in enumerate(self.vfilters):
                perm_matches[idx] = bool(f(perm))
            perm_matches['ports'] = self.process_ports(perm)
            perm_matches['cidrs'] = self.process_cidrs(perm)
            perm_matches['self-refs'] = self.process_self_reference(perm, sg_id)
            perm_match_values = list(filter(
                lambda x: x is not None, perm_matches.values()))

            # account for one python behavior any([]) == False, all([]) == True
            if match_op == all and not perm_match_values:
                continue

            match = match_op(perm_match_values)
            if match:
                matched.append(perm)

        if matched:
            resource['Matched%s' % self.ip_permissions_key] = matched
            return True


@SecurityGroup.filter_registry.register('ingress')
class IPPermission(SGPermission):

    ip_permissions_key = "IpPermissions"
    schema = {
        'type': 'object',
        # 'additionalProperties': True,
        'properties': {
            'type': {'enum': ['ingress']},
            'match-operator': {'type': 'string', 'enum': ['or', 'and']},
            'Ports': {'type': 'array', 'items': {'type': 'integer'}},
            'SelfReference': {'type': 'boolean'}
        },
        'required': ['type']}


@SecurityGroup.filter_registry.register('egress')
class IPPermissionEgress(SGPermission):

    ip_permissions_key = "IpPermissionsEgress"
    schema = {
        'type': 'object',
        # 'additionalProperties': True,
        'properties': {
            'type': {'enum': ['egress']},
            'match-operator': {'type': 'string', 'enum': ['or', 'and']},
            'SelfReference': {'type': 'boolean'}
        },
        'required': ['type']}


@SecurityGroup.action_registry.register('delete')
class Delete(BaseAction):
    """Action to delete security group(s)

    It is recommended to apply a filter to the delete policy to avoid the
    deletion of all security groups returned.

    :example:

    .. code-block:: yaml

            policies:
              - name: security-groups-unused-delete
                resource: security-group
                filters:
                  - type: unused
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('ec2:DeleteSecurityGroup',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            client.delete_security_group(GroupId=r['GroupId'])


@SecurityGroup.action_registry.register('remove-permissions')
class RemovePermissions(BaseAction):
    """Action to remove ingress/egress rule(s) from a security group

    :example:

    .. code-block:: yaml

            policies:
              - name: security-group-revoke-8080
                resource: security-group
                filters:
                  - type: ingress
                    IpProtocol: tcp
                    FromPort: 0
                    GroupName: http-group
                actions:
                  - type: remove-permissions
                    ingress: matched

    """
    schema = type_schema(
        'remove-permissions',
        ingress={'type': 'string', 'enum': ['matched', 'all']},
        egress={'type': 'string', 'enum': ['matched', 'all']})

    permissions = ('ec2:RevokeSecurityGroupIngress',
                   'ec2:RevokeSecurityGroupEgress')

    def process(self, resources):
        i_perms = self.data.get('ingress', 'matched')
        e_perms = self.data.get('egress', 'matched')

        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            for label, perms in [('ingress', i_perms), ('egress', e_perms)]:
                if perms == 'matched':
                    key = 'MatchedIpPermissions%s' % (
                        label == 'egress' and 'Egress' or '')
                    groups = r.get(key, ())
                elif perms == 'all':
                    key = 'IpPermissions%s' % (
                        label == 'egress' and 'Egress' or '')
                    groups = r.get(key, ())
                elif isinstance(perms, list):
                    groups = perms
                else:
                    continue
                if not groups:
                    continue
                method = getattr(client, 'revoke_security_group_%s' % label)
                method(GroupId=r['GroupId'], IpPermissions=groups)


@resources.register('eni')
class NetworkInterface(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'eni'
        enum_spec = ('describe_network_interfaces', 'NetworkInterfaces', None)
        name = id = 'NetworkInterfaceId'
        filter_name = 'NetworkInterfaceIds'
        filter_type = 'list'
        dimension = None
        date = None
        config_type = "AWS::EC2::NetworkInterface"
        id_prefix = "eni-"

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeENI(self)
        elif source_type == 'config':
            return query.ConfigSource(self)
        raise ValueError("invalid source %s" % source_type)


class DescribeENI(query.DescribeSource):

    def augment(self, resources):
        for r in resources:
            r['Tags'] = r.pop('TagSet', [])
        return resources


NetworkInterface.filter_registry.register('flow-logs', FlowLogFilter)
NetworkInterface.filter_registry.register(
    'network-location', net_filters.NetworkLocation)


@NetworkInterface.filter_registry.register('subnet')
class InterfaceSubnetFilter(net_filters.SubnetFilter):
    """Network interface subnet filter

    :example:

    .. code-block:: yaml

            policies:
              - name: network-interface-in-subnet
                resource: eni
                filters:
                  - type: subnet
                    key: CidrBlock
                    value: 10.0.2.0/24
    """

    RelatedIdsExpression = "SubnetId"


@NetworkInterface.filter_registry.register('security-group')
class InterfaceSecurityGroupFilter(net_filters.SecurityGroupFilter):
    """Network interface security group filter

    :example:

    .. code-block:: yaml

            policies:
              - name: network-interface-ssh
                resource: eni
                filters:
                  - type: security-group
                    match-resource: true
                    key: FromPort
                    value: 22
    """

    RelatedIdsExpression = "Groups[].GroupId"


@NetworkInterface.action_registry.register('modify-security-groups')
class InterfaceModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):
    """Remove security groups from an interface.

    Can target either physical groups as a list of group ids or
    symbolic groups like 'matched' or 'all'. 'matched' uses
    the annotations of the 'group' interface filter.

    Note an interface always gets at least one security group, so
    we also allow specification of an isolation/quarantine group
    that can be specified if there would otherwise be no groups.


    :example:

    .. code-block:: yaml

            policies:
              - name: network-interface-remove-group
                resource: eni
                filters:
                  - type: security-group
                    match-resource: true
                    key: FromPort
                    value: 22
                actions:
                  - type: remove-groups
                    groups: matched
                    isolation-group: sg-01ab23c4
    """
    permissions = ('ec2:ModifyNetworkInterfaceAttribute',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        groups = super(
            InterfaceModifyVpcSecurityGroups, self).get_groups(resources)
        for idx, r in enumerate(resources):
            client.modify_network_interface_attribute(
                NetworkInterfaceId=r['NetworkInterfaceId'],
                Groups=groups[idx])


@resources.register('route-table')
class RouteTable(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'route-table'
        enum_spec = ('describe_route_tables', 'RouteTables', None)
        name = id = 'RouteTableId'
        filter_name = 'RouteTableIds'
        filter_type = 'list'
        date = None
        dimension = None
        id_prefix = "rtb-"


@RouteTable.filter_registry.register('subnet')
class SubnetRoute(net_filters.SubnetFilter):
    """Filter a route table by its associated subnet attributes."""

    RelatedIdsExpression = "Associations[].SubnetId"

    RelatedMapping = None

    def get_related_ids(self, resources):
        if self.RelatedIdMapping is None:
            return super(SubnetRoute, self).get_related_ids(resources)
        return list(itertools.chain(*[self.RelatedIdMapping[r['RouteTableId']] for r in resources]))

    def get_related(self, resources):
        rt_subnet_map = {}
        main_tables = {}

        manager = self.get_resource_manager()
        for r in resources:
            rt_subnet_map[r['RouteTableId']] = []
            for a in r.get('Associations', ()):
                if 'SubnetId' in a:
                    rt_subnet_map[r['RouteTableId']].append(a['SubnetId'])
                elif a.get('Main'):
                    main_tables[r['VpcId']] = r['RouteTableId']
        explicit_subnet_ids = set(itertools.chain(*rt_subnet_map.values()))
        subnets = manager.resources()
        for s in subnets:
            if s['SubnetId'] in explicit_subnet_ids:
                continue
            if s['VpcId'] not in main_tables:
                continue
            rt_subnet_map.setdefault(main_tables[s['VpcId']], []).append(s['SubnetId'])
        related_subnets = set(itertools.chain(*rt_subnet_map.values()))
        self.RelatedIdMapping = rt_subnet_map
        return {s['SubnetId']: s for s in subnets if s['SubnetId'] in related_subnets}


@RouteTable.filter_registry.register('route')
class Route(ValueFilter):
    """Filter a route table by its routes' attributes."""

    schema = type_schema('route', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        results = []
        for r in resources:
            matched = []
            for route in r['Routes']:
                if self.match(route):
                    matched.append(route)
            if matched:
                r.setdefault('c7n:matched-routes', []).extend(matched)
                results.append(r)
        return results


@resources.register('peering-connection')
class PeeringConnection(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'vpc-peering-connection'
        enum_spec = ('describe_vpc_peering_connections',
                     'VpcPeeringConnections', None)
        name = id = 'VpcPeeringConnectionId'
        filter_name = 'VpcPeeringConnectionIds'
        filter_type = 'list'
        date = None
        dimension = None
        id_prefix = "pcx-"


@PeeringConnection.filter_registry.register('cross-account')
class CrossAccountPeer(CrossAccountAccessFilter):

    schema = type_schema(
        'cross-account',
        # white list accounts
        whitelist_from=resolver.ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}})

    permissions = ('ec2:DescribeVpcPeeringConnections',)

    def process(self, resources, event=None):
        results = []
        accounts = self.get_accounts()
        owners = map(jmespath.compile, (
            'AccepterVpcInfo.OwnerId', 'RequesterVpcInfo.OwnerId'))

        for r in resources:
            for o_expr in owners:
                account_id = o_expr.search(r)
                if account_id and account_id not in accounts:
                    r.setdefault(
                        'c7n:CrossAccountViolations', []).append(account_id)
                    results.append(r)
        return results


@PeeringConnection.filter_registry.register('missing-route')
class MissingRoute(Filter):
    """Return peers which are missing a route in route tables.

    If the peering connection is between two vpcs in the same account,
    the connection is returned unless it is in present route tables in
    each vpc.

    If the peering connection is between accounts, then the local vpc's
    route table is checked.
    """

    schema = type_schema('missing-route')
    permissions = ('ec2:DescribeRouteTables',)

    def process(self, resources, event=None):
        tables = self.manager.get_resource_manager(
            'route-table').resources()
        routed_vpcs = {}
        mid = 'VpcPeeringConnectionId'
        for t in tables:
            for r in t.get('Routes', ()):
                if mid in r:
                    routed_vpcs.setdefault(r[mid], []).append(t['VpcId'])
        results = []
        for r in resources:
            if r[mid] not in routed_vpcs:
                results.append(r)
                continue
            for k in ('AccepterVpcInfo', 'RequesterVpcInfo'):
                if r[k]['OwnerId'] != self.manager.config.account_id:
                    continue
                if r[k].get('Region') and r['k']['Region'] != self.manager.config.region:
                    continue
                if r[k]['VpcId'] not in routed_vpcs[r['VpcPeeringConnectionId']]:
                    results.append(r)
                    break
        return results


@resources.register('network-acl')
class NetworkAcl(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'network-acl'
        enum_spec = ('describe_network_acls', 'NetworkAcls', None)
        name = id = 'NetworkAclId'
        filter_name = 'NetworkAclIds'
        filter_type = 'list'
        date = None
        dimension = None
        config_type = "AWS::EC2::NetworkAcl"
        id_prefix = "acl-"


@NetworkAcl.filter_registry.register('subnet')
class AclSubnetFilter(net_filters.SubnetFilter):
    """Filter network acls by the attributes of their attached subnets.

    :example:

    .. code-block:: yaml

            policies:
              - name: subnet-acl
                resource: network-acl
                filters:
                  - type: subnet
                    key: "tag:Location"
                    value: Public
    """

    RelatedIdsExpression = "Associations[].SubnetId"


@NetworkAcl.filter_registry.register('s3-cidr')
class AclAwsS3Cidrs(Filter):
    """Filter network acls by those that allow access to s3 cidrs.

    Defaults to filtering those nacls that do not allow s3 communication.

    :example:

        Find all nacls that do not allow communication with s3.

    .. code-block:: yaml

            policies:
              - name: s3-not-allowed-nacl
                resource: network-acl
                filters:
                  - s3-cidr
    """
    # TODO allow for port specification as range
    schema = type_schema(
        's3-cidr',
        egress={'type': 'boolean', 'default': True},
        ingress={'type': 'boolean', 'default': True},
        present={'type': 'boolean', 'default': False})

    permissions = ('ec2:DescribePrefixLists',)

    def process(self, resources, event=None):
        ec2 = local_session(self.manager.session_factory).client('ec2')
        cidrs = jmespath.search(
            "PrefixLists[].Cidrs[]", ec2.describe_prefix_lists())
        cidrs = [parse_cidr(cidr) for cidr in cidrs]
        results = []

        check_egress = self.data.get('egress', True)
        check_ingress = self.data.get('ingress', True)
        present = self.data.get('present', False)

        for r in resources:
            matched = {cidr: None for cidr in cidrs}
            for entry in r['Entries']:
                if entry['Egress'] and not check_egress:
                    continue
                if not entry['Egress'] and not check_ingress:
                    continue
                entry_cidr = parse_cidr(entry['CidrBlock'])
                for c in matched:
                    if c in entry_cidr and matched[c] is None:
                        matched[c] = (
                            entry['RuleAction'] == 'allow' and True or False)
            if present and all(matched.values()):
                results.append(r)
            elif not present and not all(matched.values()):
                results.append(r)
        return results


@resources.register('network-addr')
class NetworkAddress(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'eip-allocation'
        enum_spec = ('describe_addresses', 'Addresses', None)
        name = 'PublicIp'
        id = 'AllocationId'
        filter_name = 'PublicIps'
        filter_type = 'list'
        date = None
        dimension = None
        config_type = "AWS::EC2::EIP"

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                self.get_model().service,
                region=self.config.region,
                account_id=self.account_id,
                resource_type=self.resource_type.type,
                separator='/')
        return self._generate_arn

    def get_arn(self, r):
        return self.generate_arn(r[self.get_model().id])

    def get_arns(self, resource_set):
        arns = []
        for r in resource_set:
            _id = r[self.get_model().id]
            arns.append(self.generate_arn(_id))
        return arns


NetworkAddress.filter_registry.register('shield-enabled', IsShieldProtected)
NetworkAddress.action_registry.register('set-shield', SetShieldProtection)


@NetworkAddress.action_registry.register('release')
class AddressRelease(BaseAction):
    """Action to release elastic IP address(es)

    Use the force option to cause any attached elastic IPs to
    also be released.  Otherwise, only unattached elastic IPs
    will be released.

    :example:

    .. code-block:: yaml

            policies:
              - name: release-network-addr
                resource: network-addr
                filters:
                  - AllocationId: ...
                actions:
                  - type: release
                    force: true|false
    """

    schema = type_schema('release', force={'type': 'boolean'})
    permissions = ('ec2:ReleaseAddress', 'ec2:DisassociateAddress',)

    def process_attached(self, client, associated_addrs):
        for aa in list(associated_addrs):
            try:
                client.disassociate_address(AssociationId=aa['AssociationId'])
            except BotoClientError as e:
                # If its already been diassociated ignore, else raise.
                if not(e.response['Error']['Code'] == 'InvalidAssocationID.NotFound' and
                       aa['AssocationId'] in e.response['Error']['Message']):
                    raise e
                associated_addrs.remove(aa)
        return associated_addrs

    def process(self, network_addrs):
        client = local_session(self.manager.session_factory).client('ec2')
        force = self.data.get('force')
        assoc_addrs = [addr for addr in network_addrs if 'AssociationId' in addr]
        unassoc_addrs = [addr for addr in network_addrs if 'AssociationId' not in addr]

        if len(assoc_addrs) and not force:
            self.log.warning(
                "Filtered %d attached eips of %d eips. Use 'force: true' to release them.",
                len(assoc_addrs), len(network_addrs))
        elif len(assoc_addrs) and force:
            unassoc_addrs = itertools.chain(
                unassoc_addrs, self.process_attached(client, assoc_addrs))

        for r in unassoc_addrs:
            try:
                client.release_address(AllocationId=r['AllocationId'])
            except BotoClientError as e:
                # If its already been released, ignore, else raise.
                if e.response['Error']['Code'] == 'InvalidAllocationID.NotFound':
                    raise


@resources.register('customer-gateway')
class CustomerGateway(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'customer-gateway'
        enum_spec = ('describe_customer_gateways', 'CustomerGateways', None)
        detail_spec = None
        id = 'CustomerGatewayId'
        filter_name = 'CustomerGatewayIds'
        filter_type = 'list'
        name = 'CustomerGatewayId'
        date = None
        dimension = None
        id_prefix = "cgw-"


@resources.register('internet-gateway')
class InternetGateway(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'internet-gateway'
        enum_spec = ('describe_internet_gateways', 'InternetGateways', None)
        name = id = 'InternetGatewayId'
        filter_name = 'InternetGatewayIds'
        filter_type = 'list'
        dimension = None
        date = None
        config_type = "AWS::EC2::InternetGateway"
        id_prefix = "igw-"


@resources.register('nat-gateway')
class NATGateway(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'nat-gateway'
        enum_spec = ('describe_nat_gateways', 'NatGateways', None)
        name = id = 'NatGatewayId'
        filter_name = 'NatGatewayIds'
        filter_type = 'list'
        dimension = None
        date = 'CreateTime'
        id_prefix = "nat-"


@NATGateway.action_registry.register('delete')
class DeleteNATGateway(BaseAction):

    schema = type_schema('delete')
    permissions = ('ec2:DeleteNatGateway',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            client.delete_nat_gateway(NatGatewayId=r['NatGatewayId'])


@resources.register('vpn-connection')
class VPNConnection(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'vpc-connection'
        enum_spec = ('describe_vpn_connections', 'VpnConnections', None)
        name = id = 'VpnConnectionId'
        filter_name = 'VpnConnectionIds'
        filter_type = 'list'
        dimension = None
        date = None
        config_type = 'AWS::EC2::VPNConnection'
        id_prefix = "vpn-"


@resources.register('vpn-gateway')
class VPNGateway(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'vpc-gateway'
        enum_spec = ('describe_vpn_gateways', 'VpnGateways', None)
        name = id = 'VpnGatewayId'
        filter_name = 'VpnGatewayIds'
        filter_type = 'list'
        dimension = None
        date = None
        config_type = 'AWS::EC2::VPNGateway'
        id_prefix = "vgw-"


@resources.register('vpc-endpoint')
class VpcEndpoint(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'vpc-endpoint'
        enum_spec = ('describe_vpc_endpoints', 'VpcEndpoints', None)
        name = id = 'VpcEndpointId'
        date = 'CreationTimestamp'
        filter_name = 'VpcEndpointIds'
        filter_type = 'list'
        dimension = None
        id_prefix = "vpce-"


@VpcEndpoint.filter_registry.register('security-group')
class EndpointSecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "Groups[].GroupId"


@VpcEndpoint.filter_registry.register('subnet')
class EndpointSubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "SubnetIds[]"


@resources.register('key-pair')
class KeyPair(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'key-pair'
        enum_spec = ('describe_key_pairs', 'KeyPairs', None)
        detail_spec = None
        id = 'KeyName'
        filter_name = 'KeyNames'
        name = 'KeyName'
        date = None
        dimension = None


@Vpc.action_registry.register('set-flow-log')
@Subnet.action_registry.register('set-flow-log')
@NetworkInterface.action_registry.register('set-flow-log')
class CreateFlowLogs(BaseAction):
    """Create flow logs for a network resource

    :example:

    .. code-block: yaml

        policies:
          - name: vpc-enable-flow-logs
            resource: vpc
            filters:
              - type: flow-logs
                enabled: false
            actions:
              - type: set-flow-log
                DeliverLogsPermissionArn: arn:iam:role
                LogGroupName: /custodian/vpc/flowlogs/
    """
    permissions = ('ec2:CreateFlowLogs',)
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['set-flow-log']},
            'state': {'type': 'boolean'},
            'DeliverLogsPermissionArn': {'type': 'string'},
            'LogGroupName': {'type': 'string'},
            'TrafficType': {'type': 'string',
                            'enum': ['ACCEPT', 'REJECT', 'ALL']}
        }
    }

    RESOURCE_ALIAS = {
        'vpc': 'VPC',
        'subnet': 'Subnet',
        'eni': 'NetworkInterface'
    }

    def validate(self):
        self.state = self.data.get('state', True)
        if self.state:
            if not self.data.get('DeliverLogsPermissionArn'):
                raise PolicyValidationError(
                    'DeliverLogsPermissionArn required when '
                    'creating flow-logs on %s' % (self.manager.data,))
            if not self.data.get('LogGroupName'):
                raise ValueError(
                    'LogGroupName required when creating flow-logs on %s' % (
                        self.manager.data))
        return self

    def delete_flow_logs(self, client, rids):
        flow_logs = client.describe_flow_logs(
            Filters=[{'Name': 'resource-id', 'Values': rids}])['FlowLogs']

        try:
            results = client.delete_flow_logs(
                FlowLogIds=[f['FlowLogId'] for f in flow_logs])

            for r in results['Unsuccessful']:
                self.log.exception(
                    'Exception: delete flow-log for %s: %s on %s',
                    r['ResourceId'], r['Error']['Message'])
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidParameterValue':
                self.log.exception(
                    'delete flow-log: %s', e.response['Error']['Message'])
            else:
                raise

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        params = dict(self.data)
        params.pop('type')

        if self.data.get('state'):
            params.pop('state')

        model = self.manager.get_model()
        params['ResourceIds'] = [r[model.id] for r in resources]

        if not self.state:
            self.delete_flow_logs(client, params['ResourceIds'])
            return

        params['ResourceType'] = self.RESOURCE_ALIAS[model.type]
        params['TrafficType'] = self.data.get('TrafficType', 'ALL').upper()

        try:
            results = client.create_flow_logs(**params)

            for r in results['Unsuccessful']:
                self.log.exception(
                    'Exception: create flow-log for %s: %s',
                    r['ResourceId'], r['Error']['Message'])
        except ClientError as e:
            if e.response['Error']['Code'] == 'FlowLogAlreadyExists':
                self.log.exception(
                    'Exception: create flow-log: %s',
                    e.response['Error']['Message'])
            else:
                raise
