
from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('ecs')
class ECSCluster(QueryResourceManager):

    class Meta(object):
        services = 'ecs'
        enum_spec = ('describe_clusters', 'clusters', None)
        name = "clusterName"
        id = "clusterArn"
