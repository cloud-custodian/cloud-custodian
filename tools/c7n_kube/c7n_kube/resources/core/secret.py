# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#

from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register("secret")
class Secret(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "Core"
        canonical_group = ""
        version = "V1"
        patch = "patch_namespaced_secret"
        delete = "delete_namespaced_secret"
        enum_spec = ("list_secret_for_all_namespaces", "items", None)
        plural = "secrets"
