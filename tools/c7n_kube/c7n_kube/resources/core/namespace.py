# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register("namespace")
class Namespace(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "Core"
        canonical_group = ""
        version = "V1"
        namespaced = False
        patch = "patch_namespace"
        delete = "delete_namespace"
        enum_spec = ("list_namespace", "items", None)
        plural = "namespaces"
