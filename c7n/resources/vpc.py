
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

    resource_type = 'aws.ec2.vpc-peer-connection'


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
