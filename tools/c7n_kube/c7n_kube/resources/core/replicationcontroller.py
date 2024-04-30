# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register("replication-controller")
class ReplicationController(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "Core"
        canonical_group = ""
        version = "V1"
        patch = "patch_namespaced_replication_controller"
        delete = "delete_namespaced_replication_controller"
        enum_spec = ("list_replication_controller_for_all_namespaces", "items", None)
        plural = "replicationcontrollers"
