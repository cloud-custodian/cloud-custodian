# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.provider import resources


@resources.register('build')
class CloudBuild(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudbuild'
        version = 'v1'
        component = 'projects.builds.list'
        enum_spec = ('list', 'builds[]', None)
        scope = 'project'
        scope_key = 'projectId'
        name = id = "id"
        default_report_fields = ["status", "startTime", "logsURL"]
        permissions = ('cloudbuild.builds.list',)
