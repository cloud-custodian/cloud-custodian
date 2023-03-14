# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('sourcerepo')
class SourceRepository(QueryResourceManager):
    """GCP Cloud Source Repositories
    https://cloud.google.com/source-repositories/docs/reference/rest/v1/projects.repos
    """

    class resource_type(TypeInfo):
        service = 'sourcerepo'
        version = 'v1'
        component = 'projects.repos'
        enum_spec = ('list', 'repos[]', None)
        scope = 'project'
        scope_key = 'name'
        scope_template = "projects/{}"
        name = id = 'name'
        perm_service = 'source'
        default_report_fields = ["name", "size", "url"]
        urn_component = "repo"
        urn_id_segments = (-1,)  # Just use the last segment of the id in the URN
