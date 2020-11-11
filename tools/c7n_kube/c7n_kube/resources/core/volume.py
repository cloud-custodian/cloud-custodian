# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_kube.query import QueryResourceManager, TypeInfo
from c7n_kube.provider import resources


@resources.register('volume')
class PersistentVolume(QueryResourceManager):
    class resource_type(TypeInfo):
        group = 'Core'
        version = 'V1'
        namespaced = False
        patch = 'patch_persistent_volume'
        delete = 'delete_persistent_volume'
        enum_spec = ('list_persistent_volume', 'items', None)


@resources.register('volume-claim')
class PersistentVolumeClaim(QueryResourceManager):
    class resource_type(TypeInfo):
        group = 'Core'
        version = 'V1'
        patch = 'patch_namespaced_persistent_volume_claim'
        delete = 'delete_namespaced_persistent_volume_claim'
        enum_spec = ('list_persistent_volume_claim_for_all_namespaces', 'items', None)
