# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register("stateful-set")
class StatefulSet(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "Apps"
        canonical_group = "apps"
        version = "V1"
        patch = "patch_namespaced_stateful_set"
        delete = "delete_namespaced_stateful_set"
        enum_spec = ("list_stateful_set_for_all_namespaces", "items", None)
        plural = "statefulsets"
