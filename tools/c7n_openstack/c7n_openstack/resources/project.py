# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_openstack.query import QueryResourceManager, TypeInfo
from c7n_openstack.provider import resources


@resources.register('project')
class Project(QueryResourceManager):
    class resource_type(TypeInfo):
        id = 'id'
        name = 'name'
        enum_spec = ('list_projects', None)
        default_report_fields = ['id', 'name']
