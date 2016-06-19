from botocore.exceptions import ClientError

from c7n.iamaccess import CrossAccountAccessFilter
from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import local_session


@resources.register('glacier')
class Glacier(QueryResourceManager):

    class Meta(object):
        service = 'glacier'
        enum_spec = ('list_vaults', 'VaultList', None)
        name = "VaultName"
        id = "VaultARN"

    resource_type = Meta


@Glacier.filter_registry.register('cross-account')
class GlacierCrossAccountAccessFilter(CrossAccountAccessFilter):

    def process(self, resources, event=None):
        def _augment(r):
            client = local_session(
                self.manager.session_factory).client('glacier')
            try:
                r['Policy'] = client.get_vault_access_policy(
                    vaultName=r['VaultName'])
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDeniedException':
                    self.log.warning(
                        "Access denied getting policy glacier:%s",
                        r['FunctionName'])

        self.log.debug("fetching policy for %d lambdas" % len(resources))
        with self.executor_factory(max_workers=3) as w:
            resources = filter(None, w.map(_augment, resources))

        return super(GlacierCrossAccountAccessFilter, self).process(
            resources, event)
