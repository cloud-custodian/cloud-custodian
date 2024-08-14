# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_openstack.query import QueryResourceManager, TypeInfo
from c7n_openstack.provider import resources


@resources.register('secret')
class Secret(QueryResourceManager):
    class resource_type(TypeInfo):
        enum_spec = (['key_manager', 'secrets'], None)
        id = 'secret_id'
        name = 'name'
        default_report_fields = ['id', 'name', 'secret_type', 'algorithm', 'expires_at']
