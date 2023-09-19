# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import SetLabelsAction
from c7n_gcp.provider import resources
from c7n_gcp.query import ChildResourceManager, QueryResourceManager, TypeInfo

@resources.register('cloud-run-service-v2')
class CloudRunServiceV2(ChildResourceManager):

    class resource_type(TypeInfo):
        service = "run"
        version = "v2"
        component = "projects.locations.services"
        name = id = "name"
        parent_spec = {
            'resource': 'region',
            'child_enum_params': {
                ('name', 'region')
            },
            'use_child_query': True
        }
        default_report_fields = ('name', 'description', 'updateTime', 'lastModified', 'observedGeneration')
        urn_component = "services"
        urn_id_segments = (-1,)
        asset_type = "run.googleapis.com/Service"

        @classmethod
        def _get_location(cls, resource):
            resource['name'].split('/')[3]


@CloudRunServiceV2.register('set-labels')
class SetServiceLabels(SetLabelsAction):

    method_spec = {'': ''}
    method_perm = 'patch'

    def get_resource_params(self, model, resource):
        pass

    def process(self, resources):
        pass


@resources.register("cloud-run-service")
class CloudRunService(QueryResourceManager):
    """GCP resource: https://cloud.google.com/run/docs/reference/rest/v1/namespaces.services"""

    class resource_type(TypeInfo):
        service = "run"
        version = "v1"
        component = "projects.locations.services"
        enum_spec = ("list", "items[]", None)
        scope = "project"
        scope_key = "parent"
        scope_template = "projects/{}/locations/-"
        name = "metadata.name"
        id = "metadata.selfLink"
        default_report_fields = ["metadata.name", "metadata.creationTimestamp"]
        asset_type = "run.googleapis.com/Service"


@resources.register("cloud-run-job")
class CloudRunJob(QueryResourceManager):
    """GCP resource: https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs"""

    class resource_type(TypeInfo):
        service = "run"
        version = "v1"
        component = "namespaces.jobs"
        enum_spec = ("list", "items[]", None)
        scope = "project"
        scope_key = "parent"
        scope_template = "namespaces/{}"
        name = "metadata.name"
        id = "metadata.selfLink"
        default_report_fields = ["metadata.name", "metadata.creationTimestamp"]
        asset_type = "run.googleapis.com/Job"


@resources.register("cloud-run-revision")
class CloudRunRevision(QueryResourceManager):
    """GCP resource: https://cloud.google.com/run/docs/reference/rest/v2/projects.locations.services.revisions"""

    class resource_type(TypeInfo):
        service = "run"
        version = "v1"
        component = "namespaces.revisions"
        enum_spec = ("list", "items[]", None)
        scope_key = "parent"
        scope_template = "namespaces/{}"
        name = "metadata.name"
        id = "metadata.selfLink"
        default_report_fields = ["metadata.name", "metadata.creationTimestamp"]
        asset_type = "run.googleapis.com/Revision"
        urn_component = "revision"
        urn_id_segments = (-1,)
