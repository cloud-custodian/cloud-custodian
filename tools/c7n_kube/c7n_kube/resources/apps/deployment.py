# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register('deployment')
class Deployment(QueryResourceManager):

    class resource_type(TypeInfo):
        group = 'Apps'
        version = 'V1'
        patch = 'patch_namespaced_deployment'
        delete = 'delete_namespaced_deployment'
        enum_spec = ('list_deployment_for_all_namespaces', 'items', None)
