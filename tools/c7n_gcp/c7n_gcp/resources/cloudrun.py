# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy

from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.filters import IamPolicyFilter
from c7n_gcp.filters.iampolicy import IamPolicyValueFilter
from c7n.utils import local_session


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
        labels = True
        labels_op = 'replaceService'

        @staticmethod
        def get_label_params(resource, all_labels):
            metadata = resource['metadata']
            location = metadata['labels']['cloud.googleapis.com/location']
            namespace = metadata['namespace']
            svc_name = metadata['name']
            body = copy.deepcopy(resource)
            body['metadata']['labels'] = all_labels
            return {
                'name': 'projects/{}/locations/{}/services/{}'.format(
                    namespace, location, svc_name),
                'body': body
            }

    def augment(self, resources):
        for r in resources:
            if r.get('metadata', {}).get('labels'):
                r['labels'] = dict(r['metadata']['labels'])
        return resources


@CloudRunService.filter_registry.register("iam-policy")
class CloudRunServiceIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process cloudrun resources correctly.
    """
    permissions = ("run.services.getIamPolicy",)

    def _verb_arguments(self, resource):
        session = local_session(self.manager.session_factory)
        project = session.get_default_project()
        location = resource["metadata"]["labels"]["cloud.googleapis.com/location"]
        verb_arguments = {
            "resource": f'projects/{project}/locations/{location}/services/' +
                f'{resource["metadata"]["name"]}'
        }
        return verb_arguments

    def process_resources(self, resources):
        value_filter = IamPolicyValueFilter(self.data["doc"], self.manager)
        value_filter._verb_arguments = self._verb_arguments
        return value_filter.process(resources)


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
        labels = True
        labels_op = 'replaceJob'

        @staticmethod
        def get_label_params(resource, all_labels):
            metadata = resource['metadata']
            namespace = metadata['namespace']
            job_name = metadata['name']
            body = copy.deepcopy(resource)
            body['metadata']['labels'] = all_labels
            return {
                'name': 'namespaces/{}/jobs/{}'.format(namespace, job_name),
                'body': body
            }

    def augment(self, resources):
        for r in resources:
            if r.get('metadata', {}).get('labels'):
                r['labels'] = dict(r['metadata']['labels'])
        return resources


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
