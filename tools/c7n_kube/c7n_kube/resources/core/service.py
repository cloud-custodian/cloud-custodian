# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register('service')
class Service(QueryResourceManager):
    class resource_type(TypeInfo):
        group = 'Core'
        version = 'V1'
        patch = 'patch_namespaced_service'
        delete = 'delete_namespaced_service'
        enum_spec = ('list_service_for_all_namespaces', 'items', None)
