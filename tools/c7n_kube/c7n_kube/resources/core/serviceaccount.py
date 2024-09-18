# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register("service-account")
class ServiceAccount(QueryResourceManager):
    class resource_type(TypeInfo):
        group = "Core"
        canonical_group = ""
        version = "V1"
        patch = "patch_namespaced_service_account"
        delete = "delete_namespaced_service_account"
        enum_spec = ("list_service_account_for_all_namespaces", "items", None)
        plural = "serviceaccounts"
