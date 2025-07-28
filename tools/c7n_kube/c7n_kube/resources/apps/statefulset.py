# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources
from c7n.filters.offhours import OffHour, OnHour


@resources.register("stateful-set")
class StatefulSet(QueryResourceManager):
    class resource_type(TypeInfo):
        group = 'Apps'
        version = 'V1'
        patch = 'patch_namespaced_stateful_set'
        delete = 'delete_namespaced_stateful_set'
        enum_spec = ('list_stateful_set_for_all_namespaces', 'items', None)
        plural = 'statefulsets'


StatefulSet.filter_registry.register('offhour', OffHour)
StatefulSet.filter_registry.register('onhour', OnHour)
