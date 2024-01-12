# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register("node")
class Node(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "Core"
        canonical_group = ""
        version = "V1"
        namespaced = False
        patch = "patch_node"
        delete = "delete_node"
        enum_spec = ("list_node", "items", None)
        plural = "nodes"
