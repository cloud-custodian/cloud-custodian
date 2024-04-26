# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from c7n_openstack.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n_openstack.provider import resources
from c7n.utils import local_session


class StorageContainerMeta(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client()
        results = []
        for r in resources:
            container_metadata = client.object_store.get_container_metadata(r['name']).toDict()
            if container_metadata:
                results.append(container_metadata)
        return results


@resources.register('storage-container')
class StorageContainer(QueryResourceManager):

    source_mapping = {'describe-openstack': StorageContainerMeta}

    class resource_type(TypeInfo):
        enum_spec = (['object_store', 'containers'], None)
        id = name = 'name'
        default_report_fields = ['name']
