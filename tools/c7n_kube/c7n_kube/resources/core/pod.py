# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources
from c7n.filters.offhours import OffHour, OnHour


@resources.register("pod")
class Pod(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "Core"
        canonical_group = ""
        version = "V1"
        patch = "patch_namespaced_pod"
        delete = "delete_namespaced_pod"
        enum_spec = ("list_pod_for_all_namespaces", "items", None)
        plural = "pods"


Pod.filter_registry.register('offhour', OffHour)
Pod.filter_registry.register('onhour', OnHour)
