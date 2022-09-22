# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('patch-deployment')
class PatchDeployment(QueryResourceManager):
    """ GC resource: https://cloud.google.com/compute/docs/osconfig/rest/v1/projects.patchDeployments"""
    class resource_type(TypeInfo):
        service = 'osconfig'
        version = 'v1'
        component = 'projects.patchDeployments'
        enum_spec = ('list', 'patchDeployments[]', None)
        scope_key = 'parent'
        name = id = 'id'
        scope_template = 'projects/{}'
        default_report_fields = ['displayName', 'expireTime']
