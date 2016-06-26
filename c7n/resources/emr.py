from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('emr-cluster')
class EMRCluster(QueryResourceManager):

    class Meta(object):
        service = 'emr'
        type = 'emr-cluster'
        enum_spec = ('list_clusters', 'Clusters', None)
        name = 'Name'
        id = 'Id'
        dimension = 'ClusterId'

    resource_type = Meta
        
    def augment(self, resources):
        # remap for cwmetrics
        for r in resources:
            r['ClusterId'] = r['Id']
        return resources
        

        
