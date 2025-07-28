# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources
from c7n.filters.offhours import OffHour, OnHour


@resources.register("deployment")
class Deployment(QueryResourceManager):
    class resource_type(TypeInfo):
        group = 'Apps'
        version = 'V1'
        patch = 'patch_namespaced_deployment'
        delete = 'delete_namespaced_deployment'
        enum_spec = ('list_deployment_for_all_namespaces', 'items', None)
        plural = 'deployments'


Deployment.filter_registry.register('offhour', OffHour)
Deployment.filter_registry.register('onhour', OnHour)
