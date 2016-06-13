

from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('cache-cluster')
class CacheCluster(QueryResourceManager):

    resource_type = 'aws.elasticache.cluster'


@resources.register('cache-subnet-group')
class ClusterSubnetGroup(QueryResourceManager):

    resource_type = 'aws.elasticache.subnet-group'


@resources.register('cache-snapshot')
class CacheSnapshot(QueryResourceManager):

    resource_type = 'aws.elasticache.snapshot'
