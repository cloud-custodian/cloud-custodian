

from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('hostedzone')
class HostedZone(QueryResourceManager):

    resource_type = 'aws.route53.hostedzone'


@resources.register('hostedzone')
class HealthCheck(QueryResourceManager):

    resource_type = 'aws.route53.healthcheck'
