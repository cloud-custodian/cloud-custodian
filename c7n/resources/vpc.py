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

from c7n.actions import BaseAction, ModifyGroupsAction
from c7n.filters import (
    DefaultVpcBase, Filter, FilterValidationError, ValueFilter)
import c7n.filters.vpc as net_filters
from c7n.query import QueryResourceManager, ResourceQuery
from c7n.manager import resources
from c7n.utils import local_session, type_schema


@resources.register('vpc')
class Vpc(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.ec2.vpc')):
        config_type = 'AWS::EC2::VPC'


@Vpc.filter_registry.register('subnets')
class VpcSubnets(ValueFilter):

    schema = type_schema('subnets', rinherit=ValueFilter.schema)

    def __init__(self, *args, **kw):
        super(VpcSubnets, self).__init__(*args, **kw)
        self.data['key'] = 'Subnets'

    def process(self, resources, event=None):

        subnets = Subnet(self.manager.ctx, {}).resources()

        matched = []
        for r in resources:
            r['Subnets'] = [s for s in subnets if s['VpcId'] == r['VpcId']]
            if self.match(r):
                matched.append(r)

        return matched


@resources.register('subnet')
class Subnet(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.ec2.subnet')):
        config_type = 'AWS::EC2::Subnet'


@resources.register('security-group')
class SecurityGroup(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.ec2.security-group')):
        config_type = "AWS::EC2::SecurityGroup"


class SGUsage(Filter):

    def filter_peered_refs(self, resources):
        if not resources:
            return resources
        # Check that groups are not referenced across accounts
        client = local_session(self.manager.session_factory).client('ec2')
        peered_ids = set()
        for sg_ref in client.describe_security_group_references(
                GroupId=[r['GroupId'] for r in resources]
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
        from c7n.resources.asg import LaunchConfig
        for cfg in LaunchConfig(self.manager.ctx, {}).resources():
            for g in cfg['SecurityGroups']:
                sg_ids.add(g)
            for g in cfg['ClassicLinkVPCSecurityGroups']:
                sg_ids.add(g)
        return sg_ids

    def get_lambda_sgs(self):
        sg_ids = set()
        from c7n.resources.awslambda import AWSLambda
        for func in AWSLambda(self.manager.ctx, {}).resources():
            if 'VpcConfig' not in func:
                continue
            for g in func['VpcConfig']['SecurityGroupIds']:
                sg_ids.add(g)
        return sg_ids

    def get_eni_sgs(self):
        sg_ids = set()
        for nic in NetworkInterface(self.manager.ctx, {}).resources():
            for g in nic['Groups']:
                sg_ids.add(g['GroupId'])
        return sg_ids

    def get_sg_refs(self):
        sg_ids = set()
        for sg in SecurityGroup(self.manager.ctx, {}).resources():
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
    """
    schema = type_schema('unused')

    def process(self, resources, event=None):
        used = self.scan_groups()
        unused = [
            r for r in resources
            if r['GroupId'] not in used
            and 'VpcId' in r]
        return unused and self.filter_peered_refs(unused) or []


@SecurityGroup.filter_registry.register('used')
class UsedSecurityGroup(SGUsage):
    """Filter to security groups that are used.

    This operates as a complement to the unused filter for multi-step
    workflows.
    """
    schema = type_schema('used')

    def process(self, resources, event=None):
        used = self.scan_groups()
        unused = [
            r for r in resources
            if r['GroupId'] not in used
            and 'VpcId' in r]
        unused = set(self.filter_peered_refs(unused))
        return [r for r in resources if r['GroupId'] not in unused]


@SecurityGroup.filter_registry.register('default-vpc')
class SGDefaultVpc(DefaultVpcBase):

    schema = type_schema('default-vpc')

    def __call__(self, resource, event=None):
        if 'VpcId' not in resource:
            return False
        return self.match(resource['VpcId'])


class SGPermission(Filter):
    """Base class for verifying security group permissions

    All attributes of a security group permission are available as
    value filters.

    If multiple attributes are specified the permission must satisfy
    all of them.

    If a group has any permissions that match all conditions, then it
    matches the filter.

    Permissions that match on the group are annotated onto the group and
    can subsequently be used by the remove-permission action.

    An example::

      - type: ingress
        IpProtocol: -1
        FromPort: 445

    We have specialized handling for matching Ports in ingress/egress
    permission From/To range::

      - type: ingress
        Ports: [22, 443, 80]

    As well for assertions that a ingress/egress permission only matches
    a given set of ports, *note* onlyports is an inverse match, it matches
    when a permission includes ports outside of the specified set:

      - type: egress
        OnlyPorts: [22, 443, 80]

      - type: egress
        IpRanges:
          - value_type: cidr
          - op: in
          - value: x.y.z
    """

    perm_attrs = set((
        'IpProtocol', 'FromPort', 'ToPort', 'UserIdGroupPairs',
        'IpRanges', 'PrefixListIds'))
    filter_attrs = set(('Cidr', 'Ports', 'OnlyPorts'))
    attrs = perm_attrs.union(filter_attrs)

    def validate(self):
        delta = set(self.data.keys()).difference(self.attrs)
        delta.remove('type')
        if delta:
            raise FilterValidationError("Unknown keys %s" % ", ".join(delta))
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
        found = False
        if 'FromPort' in perm and 'ToPort' in perm:
            for port in self.ports:
                if port >= perm['FromPort'] and port <= perm['ToPort']:
                    found = True
                    break
            only_found = False
            for port in self.only_ports:
                if port == perm['FromPort'] and port == perm['ToPort']:
                    only_found = True
            if self.only_ports and not only_found:
                found = True
        return found

    def process_cidrs(self, perm):
        found = False

        if 'IpRanges' in perm and 'Cidr' in self.data:
            match_range = self.data['Cidr']
            match_range['key'] = 'CidrIp'
            vf = ValueFilter(match_range)
            vf.annotate = False
            for ip_range in perm.get('IpRanges', []):
                found = vf(ip_range)
                if found:
                    break
        return found

    def __call__(self, resource):
        matched = []
        for perm in resource[self.ip_permissions_key]:
            found = False
            for f in self.vfilters:
                if f(perm):
                    found = True
                    break
            if not found:
                found = self.process_ports(perm)
            if not found:
                found = self.process_cidrs(perm)

            if not found:
                continue
            matched.append(perm)

        if matched:
            resource['Matched%s' % self.ip_permissions_key] = matched
            return True


@SecurityGroup.filter_registry.register('ingress')
class IPPermission(SGPermission):

    ip_permissions_key = "IpPermissions"
    schema = {
        'type': 'object',
        #'additionalProperties': True,
        'properties': {
            'type': {'enum': ['ingress']},
            'Ports': {'type': 'array', 'items': {'type': 'integer'}}
            },
        'required': ['type']}


@SecurityGroup.filter_registry.register('egress')
class IPPermissionEgress(SGPermission):

    ip_permissions_key = "IpPermissionsEgress"
    schema = {
        'type': 'object',
        #'additionalProperties': True,
        'properties': {
            'type': {'enum': ['egress']}
            },
        'required': ['type']}


@SecurityGroup.action_registry.register('remove-permissions')
class RemovePermissions(BaseAction):

    schema = type_schema(
        'remove-permissions',
        ingress={'type': 'string', 'enum': ['matched', 'all']},
        egress={'type': 'string', 'enum': ['matched', 'all']})

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
class NetworkInterface(QueryResourceManager):

    class Meta(object):

        service = 'ec2'
        type = 'eni'
        enum_spec = ('describe_network_interfaces', 'NetworkInterfaces', None)
        name = id = 'NetworkInterfaceId'
        filter_name = 'NetworkInterfaceIds'
        filter_type = 'list'
        dimension = None
        date = None
        config_type = "AWS::EC2::NetworkInterface"

    resource_type = Meta


@NetworkInterface.filter_registry.register('subnet')
class InterfaceSubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "SubnetId"


@NetworkInterface.filter_registry.register('security-group')
class InterfaceSecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "Groups[].GroupId"


@NetworkInterface.action_registry.register('remove-groups')
class InterfaceRemoveGroups(ModifyGroupsAction):
    """Remove security groups from an interface.

    Can target either physical groups as a list of group ids or
    symbolic groups like 'matched' or 'all'. 'matched' uses
    the annotations of the 'group' interface filter.

    Note an interface always gets at least one security group, so
    we also allow specification of an isolation/quarantine group
    that can be specified if there would otherwise be no groups.
    """

    schema = type_schema(
        'remove-groups',
        **{'groups': {'anyOf': [
            {'type': 'string', 'enum': ['matched', 'all']},
            {'type': 'array', 'items': {'type': 'string'}}]},
           'isolation-group': {'type': 'string'}})

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        groups = super(InterfaceRemoveGroups, self).get_groups(resources)
        for idx, r in enumerate(resources):
            client.modify_network_interface_attribute(
                NetworkInterfaceId=r['NetworkInterfaceId'],
                Groups=groups[idx])


@resources.register('route-table')
class RouteTable(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.ec2.route-table')):
        config_type = "AWS::EC2::RouteTable"


@resources.register('peering-connection')
class PeeringConnection(QueryResourceManager):

    class resource_type(ResourceQuery.resolve(
            'aws.ec2.vpc-peering-connection')):
        enum_spec = ('describe_vpc_peering_connections',
                     'VpcPeeringConnections', None)


@resources.register('network-acl')
class NetworkAcl(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.ec2.network-acl')):
        config_type = "AWS::EC2::NetworkAcl"


@resources.register('network-addr')
class Address(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.ec2.address')):
        config_type = "AWS::EC2::EIP"
        taggable = False


@resources.register('customer-gateway')
class CustomerGateway(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.ec2.customer-gateway')):
        config_type = "AWS::EC2::CustomerGateway"


@resources.register('internet-gateway')
class InternetGateway(QueryResourceManager):

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


@resources.register('vpn-connection')
class VPNConnection(QueryResourceManager):

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


@resources.register('vpn-gateway')
class VPNGateway(QueryResourceManager):

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


@resources.register('key-pair')
class KeyPair(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.ec2.key-pair')):
        taggable = False
