# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register('daemon-set')
class DaemonSet(QueryResourceManager):
    class resource_type(TypeInfo):
        group = 'Apps'
        version = 'V1'
        patch = 'patch_namespaced_daemon_set'
        delete = 'delete_namespaced_daemon_set'
        enum_spec = ('list_daemon_set_for_all_namespaces', 'items', None)
