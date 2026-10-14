# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.filters import IamPolicyFilter
from c7n_gcp.filters.iampolicy import IamPolicyValueFilter
from c7n.exceptions import PolicyExecutionError
from c7n.utils import local_session, jmespath_search

# The only fields the Knative schema defines at the root of a Service or a Job.
KNATIVE_FIELDS = ('apiVersion', 'kind', 'metadata', 'spec', 'status')

# Prefixes of the annotations c7n keeps on a resource. Only the colon form is
# written to a nested object; the dotted `c7n.metrics` is set at the root alone.
# Nesting matches on the colon form only, because kubernetes annotation keys -
# user controlled, and carried in `metadata.annotations` - may contain a dot but
# never a colon, and this is a whole object replace: a key dropped from the body
# is a key deleted from the service.
C7N_ANNOTATION = 'c7n:'
C7N_ROOT_ANNOTATIONS = (C7N_ANNOTATION, 'c7n.')


def _without_annotations(value):
    "Copy a value, dropping any c7n annotation held anywhere beneath it."
    if isinstance(value, dict):
        return {k: _without_annotations(v) for k, v in value.items()
                if not k.startswith(C7N_ANNOTATION)}
    if isinstance(value, list):
        return [_without_annotations(v) for v in value]
    # everything else in a decoded api response is an immutable scalar
    return value


def knative_body(resource):
    """Copy a resource into a replace request body, dropping non schema fields.

    Cloud Run replaces the whole object, so the body is the resource itself
    rather than a fragment, and the api rejects the request with a 400 on any
    field it can't place. A resource carries two kinds it can't: the top level
    `labels` key that augment() flattens out of the metadata, and the
    annotations the policy's filters leave behind - at the root, and nested
    within `spec` when a list-item filter matched on something there.

    A root field that is neither raises rather than being dropped. Under a
    whole object replace a field left out of the body is deleted from the
    service, so a field this doesn't recognize is one it cannot safely send
    or safely omit.
    """
    unrecognized = {
        k for k in resource
        if k not in KNATIVE_FIELDS and k != 'labels'
        and not k.startswith(C7N_ROOT_ANNOTATIONS)
    }
    if unrecognized:
        raise PolicyExecutionError(
            '%s %s has fields absent from the cloud run schema: %s' % (
                resource.get('kind', 'resource'),
                resource.get('metadata', {}).get('name'),
                ', '.join(sorted(unrecognized))))
    return {k: _without_annotations(v) for k, v in resource.items() if k in KNATIVE_FIELDS}


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
        labels_perm = 'update'

        @staticmethod
        def get_label_params(resource, all_labels):
            metadata = resource['metadata']
            location = metadata['labels']['cloud.googleapis.com/location']
            namespace = metadata['namespace']
            svc_name = metadata['name']
            body = knative_body(resource)
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
        labels_perm = 'update'

        @staticmethod
        def get_label_params(resource, all_labels):
            metadata = resource['metadata']
            namespace = metadata['namespace']
            job_name = metadata['name']
            body = knative_body(resource)
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

        @classmethod
        def get_metric_resource_name(cls, resource, metric_key=None):
            # Handle different metric keys for Cloud Run revisions
            # Since Cloud Run uses nested metadata structure, we must use jmespath
            if metric_key == 'resource.labels.revision_name':
                # Extract revision name (e.g., "service-00001-abc")
                return jmespath_search("metadata.name", resource)
            elif metric_key == 'resource.labels.service_name':
                # Extract service name from Knative label (e.g., "service")
                return jmespath_search('metadata.labels."serving.knative.dev/service"', resource)
            # Default: return revision name (most common case)
            return jmespath_search("metadata.name", resource)
