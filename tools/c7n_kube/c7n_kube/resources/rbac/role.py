# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register("cluster-role")
class ClusterRole(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "RbacAuthorization"
        canonical_group = "rbac.authorization.k8s.io"
        version = "V1"
        patch = "patch_cluster_role"
        delete = "delete_cluster_role"
        enum_spec = ("list_cluster_role", "items", None)
        plural = "clusterroles"
        namespaced = False


@resources.register("role")
class NamespacedRole(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "RbacAuthorization"
        canonical_group = "rbac.authorization.k8s.io"
        version = "V1"
        patch = "patch_namespaced_role"
        delete = "delete_namespaced_role"
        enum_spec = ("list_role_for_all_namespaces", "items", None)
        plural = "roles"
        namespaced = True
