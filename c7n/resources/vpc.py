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

from c7n.actions import BaseAction
from c7n.filters import (
    DefaultVpcBase, Filter, FilterValidationError, ValueFilter)

from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import local_session, type_schema

from c7n.filters import ValueFilter, Filter, FilterRegistry
from c7n.utils import local_session, type_schema


@resources.register('vpc')
class Vpc(QueryResourceManager):

    resource_type = 'aws.ec2.vpc'



@Vpc.filter_registry.register('subnets')
class SubnetsOfVpc(ValueFilter):

    schema = type_schema('subnets', rinherit=ValueFilter.schema)

    def __init__(self, *args, **kw):
        super(SubnetsOfVpc, self).__init__(*args, **kw)
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

    resource_type = 'aws.ec2.subnet'


@resources.register('security-group')
class SecurityGroup(QueryResourceManager):

    resource_type = 'aws.ec2.security-group'


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

    Permissions that match on the group are annotated onto the group.

      - type: ingress
        IpProtocol: -1
        FromPort: 445
    """

    attrs = set(('IpProtocol', 'FromPort', 'ToPort', 'UserIdGroupPairs',
                 'IpRanges', 'PrefixListIds', 'Ports'))

    def validate(self):
        delta = set(self.data.keys()).difference(self.attrs)
        delta.remove('type')
        if delta:
            raise FilterValidationError("Unknown keys %s" % ", ".join(delta))
        return self

    def process(self, resources, event=None):
        self.vfilters = []
        fattrs = list(sorted(self.attrs.intersection(self.data.keys())))
        self.ports = 'Ports' in self.data and self.data['Ports'] or ()

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

    def __call__(self, resource):
        matched = []
        for p in resource[self.ip_permissions_key]:
            found = False
            for f in self.vfilters:
                if f(p):
                    found = True
                    break
            for p in self.ports:
                if p >= resource['FromPort'] and p <= resource['ToPort']:
                    found = True
                    break
            if not found:
                continue
            matched.append(p)

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

    schema = type_schema('remove-permissions')

    def process(self, resources):
        i_perms = self.data.get('ingress')
        e_perms = self.data.get('egress')

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

    resource_type = Meta


@NetworkInterface.filter_registry.register('subnet')
class InterfaceSubnet(ValueFilter):

    schema = type_schema('subnet', rinherits=ValueFilter.schema)
    annotate = False

    def process(self, resources, event=None):
        subnets = set([r['SubnetId'] for r in resources])
        manager = Subnet(self.manager.ctx, {})
        self.subnets = {s['SubnetId']: s for s
                        in manager.get_resources(list(subnets))}
        return super(InterfaceSubnet, self).process(resources, event)

    def __call__(self, resource):
        return self.match(self.subnets[resource['SubnetId']])


@NetworkInterface.filter_registry.register('group')
class InterfaceGroup(ValueFilter):

    annotate = False
    schema = type_schema('group', rinherits=ValueFilter.schema)

    def process(self, resources, event=None):
        groups = set()
        for r in resources:
            for g in r['Groups']:
                groups.add(g['GroupId'])
        manager = SecurityGroup(self.manager.ctx, {})
        self.groups = {s['GroupId']: s for s
                       in manager.resources()}
        # todo, something odd here
        #in manager.get_resources(sorted(list(groups)))}
        return super(InterfaceGroup, self).process(resources, event)

    def __call__(self, resource):
        matched = []
        for g in resource.get('Groups', ()):
            if self.match(self.groups[g['GroupId']]):
                matched.append(g['GroupId'])
        if matched:
            resource['MatchedSecurityGroups'] = matched
            return True


@NetworkInterface.action_registry.register('remove-groups')
class InterfaceRemoveGroups(BaseAction):
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
        target_group_ids = self.data.get('groups')
        isolation_group = self.data.get('isolation-group')

        client = local_session(self.manager.session_factory).client('ec2')

        for r in resources:
            rgroups = [g['GroupId'] for g in r['Groups']]
            if target_group_ids == 'matched':
                group_ids = r.get('MatchedSecurityGroups', ())
            elif target_group_ids == 'all':
                group_ids = rgroups
            elif isinstance(target_group_ids, list):
                group_ids = target_group_ids
            else:
                continue

            if not group_ids:
                continue

            for g in group_ids:
                if g in rgroups:
                    rgroups.remove(g)

            if not rgroups:
                rgroups.append(isolation_group)

            client.modify_network_interface_attribute(
                NetworkInterfaceId=r['NetworkInterfaceId'],
                Groups=rgroups)


@resources.register('route-table')
class RouteTable(QueryResourceManager):

    resource_type = 'aws.ec2.route-table'


@resources.register('peering-connection')
class PeeringConnection(QueryResourceManager):

    resource_type = 'aws.ec2.vpc-peering-connection'


@resources.register('network-acl')
class NetworkAcl(QueryResourceManager):

    resource_type = 'aws.ec2.network-acl'


@resources.register('network-addr')
class Address(QueryResourceManager):

    resource_type = 'aws.ec2.address'


@resources.register('customer-gateway')
class CustomerGateway(QueryResourceManager):

    resource_type = 'aws.ec2.customer-gateway'


@resources.register('internet-gateway')
class InternetGateway(QueryResourceManager):

    class Meta(object):

        service = 'ec2'
        type = 'internet-gateway'
        enum_spec = ('describe_internet_gateways', 'InternetGateways', None)
        name = id = 'InternetGatewayId'
        filter_name = 'InternetGatewayIds'
        filter_type = 'list'
        dimension = None
        date = None

    resource_type = Meta

@resources.register('key-pair')
class KeyPair(QueryResourceManager):

    resource_type = 'aws.ec2.key-pair'
