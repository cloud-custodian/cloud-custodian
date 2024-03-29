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
        name = id = 'name'
        scope_template = 'projects/{}'
        default_report_fields = ['name', 'description', 'createTime', 'state', 'rollout.mode']
        asset_type = 'osconfig.googleapis.com/PatchDeployment'
        urn_component = "patchDeployment"
        urn_id_path = "name"
        urn_id_segments = (-1,)
