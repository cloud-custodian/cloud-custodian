# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register("config-map")
class ConfigMap(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "Core"
        canonical_group = ""
        version = "V1"
        patch = "patch_namespaced_config_map"
        delete = "delete_namespaced_config_map"
        enum_spec = ("list_config_map_for_all_namespaces", "items", None)
        plural = "configmaps"
