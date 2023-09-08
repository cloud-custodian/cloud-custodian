# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


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
