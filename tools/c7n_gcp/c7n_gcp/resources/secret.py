# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import (QueryResourceManager, TypeInfo)


@resources.register('secret')
class Secret(QueryResourceManager):
    """GCP resource: https://cloud.google.com/secret-manager/docs/reference/rest/v1/projects.secrets
    """
    class resource_type(TypeInfo):
        service = 'secretmanager'
        version = 'v1'
        component = 'projects.secrets'
        enum_spec = ('list', 'secrets[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = "projects/{}"
        name = id = "name"
        asset_type = "secretmanager.googleapis.com/Secret"
        default_report_fields = ['name', 'createTime', 'expireTime', 'ttl']
