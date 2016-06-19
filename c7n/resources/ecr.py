
from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('ecr')
class ECR(QueryResourceManager):

    class Meta(object):
        services = 'ecr'
        enum_spec = ('describe_repositories', 'repositories', None)
        name = "repositoryName"
        id = "repositoryArn"


