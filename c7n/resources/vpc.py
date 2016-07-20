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

from c7n.filters.core import ValueFilter
from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import local_session


@resources.register('vpc')
class Vpc(QueryResourceManager):

    resource_type = 'aws.ec2.vpc'


@resources.register('subnet')
class Subnet(QueryResourceManager):

    resource_type = 'aws.ec2.subnet'


@resources.register('security-group')
class SecurityGroup(QueryResourceManager):

    resource_type = 'aws.ec2.security-group'


class SGPermission(ValueFilter):
    """Base class for verifying security group permissions

    All attributes of a security group permission are available as value filters.

    If multiple attributes are specified the permission must satisfy all of them.

    If a group has any permissions that match all conditions, then it matches the
    filter.

    Permissions that match on the group are annotated onto the group.
    """

    attrs = set('IpProtocol', 'FromPort', 'ToPort', 'UserIdGroupPairs', 
                'IpRanges', 'PrefixListIds')

    def process(self, resources, event=None):
        self.vfilters = []
        fattrs = list(sorted(self.attrs.intersection(self.data.keys())))

        for f in fattrs:
            fv = self.data.get(f)
            if isinstance(fv, dict):
                fv['key'] = f
            else:
                fv = {f: fv}
            vf = ValueFilter(fv)
            vf.annotate = False
            self.vfilters.append(vf)

    def __call__(self, resource):
        matched = []
        for p in resource[self.ip_permissions_key]:
            found = True
            for f in self.vfilters:
                if not f(r):
                    found = False
                    break
            if not found:
                continue
            matched.append(p)

        if matched:
            resource['Matched%s' % self.ip_permissions_key] = matched
            return True


@SecurityGroup.filters_registry.register('ingress')
class IPPermission(SGPermission):

    ip_permissions_key = "IpPermissions"


@SecurityGroup.filters_registry.register('egress')
class IPPermissionEgress(SGPermission):

    ip_permissions_key = "IpPermissionsEgress"


@SecurityGroup.actions_registry.register('remove-permissions')
class RemovePermisssions(BaseAction):

    def process(self, resources):

        i_perms = self.data.get('ingress')
        e_perms = self.data.get('egress')

        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            for label, perms in [('ingress', i_perms), ('egress', e_perms)]:
                if perms == 'matched':
                    groups = r.get('MatchedIpPermissions%s' % (
                        label == 'ingress' and '' or 'Egress'), ())
                elif perms == 'all':
                    groups = r['IpPermissions%s' % (
                        label == 'ingress' and '' or 'Egress')]
                elif isinstance(perms, list):
                   groups = perms

                if not groups:
                    continue
                method = getattr(client, 'revoke_security_group_%s' % label)
                method(GroupId=r['GroupId'], IpPermissions=groups)


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
