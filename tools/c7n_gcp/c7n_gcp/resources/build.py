# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.provider import resources


@resources.register('build')
class CloudBuild(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudbuild'
        version = 'v1'
        component = 'projects.builds'
        enum_spec = ('list', 'builds[]', None)
        scope = 'project'
        scope_key = 'projectId'
        name = id = "id"
        default_report_fields = ["status", "startTime", "logUrl"]
        permissions = ('cloudbuild.builds.list',)

        # Lacking a test so can't confirm any URN.
        urn_component = "build"
