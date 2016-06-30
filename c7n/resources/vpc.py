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

from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('vpc')
class Vpc(QueryResourceManager):

    resource_type = 'aws.ec2.vpc'


@resources.register('subnet')
class Subnet(QueryResourceManager):

    resource_type = 'aws.ec2.subnet'


@resources.register('security-group')
class SecurityGroup(QueryResourceManager):

    resource_type = 'aws.ec2.security-group'


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
