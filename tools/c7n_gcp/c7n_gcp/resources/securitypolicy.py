# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('security-policy')
class SecurityPolicy(QueryResourceManager):
    """GC resource:
        https://cloud.google.com/bigtable/docs/reference/admin/rest/v2/projects.instances"""
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'securityPolicies'
        scope_key = 'project'
        name = id = 'id'
        scope_template = '{}'
        permissions = ('compute.securityPolicies.list',)
        default_report_fields = ['displayName', 'expireTime']
