# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources
from c7n.filters.offhours import OffHour, OnHour


@resources.register("replica-set")
class ReplicaSet(QueryResourceManager):
    class resource_type(TypeInfo):
        group = 'Apps'
        version = 'V1'
        patch = 'patch_namespaced_replica_set'
        delete = 'delete_namespaced_replica_set'
        enum_spec = ('list_replica_set_for_all_namespaces', 'items', None)
        plural = 'replicasets'


ReplicaSet.filter_registry.register('offhour', OffHour)
ReplicaSet.filter_registry.register('onhour', OnHour)
