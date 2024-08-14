# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_openstack.query import QueryResourceManager, TypeInfo
from c7n_openstack.provider import resources


@resources.register('security-group')
class SecurityGroup(QueryResourceManager):
    class resource_type(TypeInfo):
        enum_spec = ('list_security_groups', None)
        id = 'id'
        name = 'name'
        default_report_fields = ['id', 'name', 'tenant_id']

    def resources(self, query=None):
        q = query or self.get_resource_query()
        key = self.get_cache_key(q)
        resources = [r.toDict() for r in self.augment(self.source.get_resources(q))]
        self._cache.save(key, resources)
        return self.filter_resources(resources)
