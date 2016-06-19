from botocore.exceptions import ClientError

from c7n.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session


@resources.register('ecr')
class ECR(QueryResourceManager):

    class Meta(object):
        service = 'ecr'
        enum_spec = ('describe_repositories', 'repositories', None)
        name = "repositoryName"
        id = "repositoryArn"

    resource_type = Meta


@ECR.filter_registry.register('cross-account')
class ECRCrossAccountAccessFilter(CrossAccountAccessFilter):

    def process(self, resources, event=None):

        def _augment(r):
            client = local_session(self.manager.session_factory).client('ecr')
            try:
                r['Policy'] = client.get_repository_policy(
                    repositoryName=r['repositoryName'])['policyText']
            except ClientError as e:
                if e.response['Error']['Code'] == 'RepositoryPolicyNotFoundException':
                    return None
                raise
            return r

        self.log.debug("fetching policy for %d repos" % len(resources))
        with self.executor_factory(max_workers=3) as w:
            resources = filter(None, w.map(_augment, resources))

        return super(ECRCrossAccountAccessFilter, self).process(resources, event)
