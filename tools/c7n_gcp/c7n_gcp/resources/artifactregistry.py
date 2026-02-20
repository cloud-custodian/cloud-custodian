from c7n.utils import local_session
from c7n_gcp.provider import resources
from c7n_gcp.query import RegionalResourceManager, ChildTypeInfo


@resources.register('artifact-repository')
class ArtifactRegistryRepository(RegionalResourceManager):
    """Artifact Registry Repository

    https://cloud.google.com/artifact-registry/docs/reference/rest/v1/projects.locations.repositories
    """
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
        default_report_fields = ['name', 'description', 'updateTime', 'sizeBytes']
        labels = True
        labels_op = 'patch'

        @staticmethod
        def get_label_params(resource, all_labels):
            return {
                'name': resource['name'],
                'body': {'labels': all_labels},
                'updateMask': 'labels'
            }

    def _get_child_enum_args(self, parent_instance):
        return {
            'parent': 'projects/{}/locations/{}'.format(
                local_session(self.session_factory).get_default_project(),
                parent_instance['name'],
            )
        }
