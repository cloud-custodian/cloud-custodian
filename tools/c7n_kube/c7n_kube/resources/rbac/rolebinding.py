# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register("cluster-role-binding")
class ClusterRoleBinding(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "RbacAuthorization"
        canonical_group = "rbac.authorization.k8s.io"
        version = "V1"
        patch = "patch_cluster_role_binding"
        delete = "delete_cluster_role_binding"
        enum_spec = ("list_cluster_role_binding", "items", None)
        plural = "clusterrolebindings"
        namespaced = False


@resources.register("role-binding")
class RoleBinding(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "RbacAuthorization"
        canonical_group = "rbac.authorization.k8s.io"
        version = "V1"
        patch = "patch_namespaced_role_binding"
        delete = "delete_namespaced_role_binding"
        enum_spec = ("list_role_binding_for_all_namespaces", "items", None)
        plural = "rolebindings"
        namespaced = True
