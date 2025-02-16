import os

from c7n.utils import local_session
from c7n_gcp.provider import resources
from c7n_gcp.query import ChildResourceManager, ChildTypeInfo
from concurrent.futures import as_completed


@resources.register('artifact-repository')
class ArtifactRegistryRepository(ChildResourceManager):
    """Artifact Registry Repository

    https://cloud.google.com/artifact-registry/docs/reference/rest/v1/projects.locations.repositories
    """
    class resource_type(ChildTypeInfo):
        service = 'artifactregistry'
        version = 'v1'
        component = 'projects.locations.repositories'
        enum_spec = ('list', 'repositories[]', None)
        scope = 'parent'
        name = id = 'name'
        parent_spec = {
            'resource': 'region',
            'child_enum_params': {
                ('name', 'region')},
            'use_child_query': False,
        }
        permissions = ('artifactregistry.repositories.list',)
        default_report_fields = ['name', 'description', 'updateTime', 'sizeBytes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._service_regions = None

    def get_service_regions(self):
        """
        Returns all available artifact-repositories regions
        :return:
        """
        if self._service_regions is not None:
            return self._service_regions
        client = local_session(self.session_factory).client(
            self.resource_type.service,
            self.resource_type.version,
            'projects.locations'
        )
        items = client.execute_command('list', verb_arguments={
            'name': f'projects/{local_session(self.session_factory).get_default_project()}'
        })
        self._service_regions = {
            item['locationId'] for item in items.get('locations', [])
        }
        return self._service_regions

    def _get_regions(self):
        """
        Returns regions according to config
        """
        regions = []
        for r in self.get_service_regions():
            if not self.config.regions or 'all' in self.config.regions or r in self.config.regions:
                regions.append({'name': r})
        return regions

    def _get_child_enum_args(self, parent_instance):
        return {
            'parent': 'projects/{}/locations/{}'.format(
                local_session(self.session_factory).get_default_project(),
                parent_instance['name'],
            )
        }

    def _get_children(self, query):
        return super(ChildResourceManager, self)._fetch_resources(query)

    def _fetch_resources(self, query):
        if not query:
            query = {}
        annotation_key = self.resource_type.get_parent_annotation_key()

        result = []
        parent_instances = self._get_regions()
        with self.executor_factory(None if os.name == 'nt' else len(parent_instances)) as w:
            futures = {}
            for parent_instance in parent_instances:
                query.update(self._get_child_enum_args(parent_instance))
                futures[w.submit(self._get_children, query)] = parent_instance
            for f in as_completed(futures):
                exc = f.exception()
                if exc:
                    self.log.error(
                        "Exception getting artifacts repositories by location \n %s" % (
                            exc)
                    )
                    continue
                children = f.result()
                for child_instance in children:
                    child_instance[annotation_key] = futures[f]
                result.extend(children)
        return result
