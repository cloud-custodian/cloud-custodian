from c7n.utils import local_session
from c7n_gcp.provider import resources
from c7n_gcp.query import RegionalResourceManager, ChildTypeInfo


@resources.register('artifactregistry-repository')
class ArtifactRegistryRepository(RegionalResourceManager):

    class resource_type(ChildTypeInfo):
        service = 'artifactregistry'
        version = 'v1'
        component = 'projects.locations.repositories'
        enum_spec = ('list', 'repositories[]', None)
        scope = 'parent'
        name = id = 'id'
        parent_spec = {
            'resource': 'region',
            'child_enum_params': {
                ('name', 'region')},
            'use_child_query': True,
        }
        permissions = ('artifactregistry.repositories.list',)
        default_report_fields = ['displayName', 'expireTime']

    def _get_child_enum_args(self, parent_instance):
        return {
            'parent': 'projects/{}/locations/{}'.format(
                local_session(self.session_factory).get_default_project(),
                parent_instance['name'],
            )
        }


# ArtifactRegistryRepository.filter_registry.register('gcp-iam-policy-filter', GCPIamPolicyFilter)
