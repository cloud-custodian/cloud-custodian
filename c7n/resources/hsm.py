# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import universal_augment
import c7n.filters.vpc as net_filters
from c7n.actions import BaseAction
from c7n.utils import local_session, type_schema


@resources.register('cloudhsm-cluster')
class CloudHSMCluster(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudhsmv2'
        arn_type = 'cluster'
        permission_prefix = arn_service = 'cloudhsm'
        enum_spec = ('describe_clusters', 'Clusters', None)
        id = name = 'ClusterId'
        filter_name = 'Filters'
        filter_type = 'scalar'
        universal_taggable = object()

    augment = universal_augment


@CloudHSMCluster.filter_registry.register('subnet')
class HSMClusterSubnet(net_filters.SubnetFilter):

    RelatedIdsExpression = ""

    def get_related_ids(self, clusters):
        subnet_ids = set()
        for cluster in clusters:
            for subnet in cluster.get('SubnetMapping').values():
                subnet_ids.add(subnet)
        return list(subnet_ids)


@CloudHSMCluster.action_registry.register('delete')
class DeleteHSMCluster(BaseAction):

    schema = type_schema('delete')
    valid_origin_states = ('UNINITIALIZED', 'INITIALIZED', 'ACTIVE', 'DEGRADED')
    permissions = ('cloudhsm:DeleteCluster',)

    def process(self, resources):
        resources = self.filter_resources(resources, 'State', self.valid_origin_states)
        client = local_session(self.manager.session_factory).client('cloudhsmv2')
        for r in resources:
            self.manager.retry(client.delete_cluster, ClusterId=r['ClusterId'], ignore_err_codes=(
                'CloudHsmResourceNotFoundException',))


@resources.register('hsm')
class CloudHSM(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudhsm'
        enum_spec = ('list_hsms', 'HsmList', None)
        arn = id = 'HsmArn'
        arn_type = 'cluster'
        name = 'Name'
        detail_spec = ("describe_hsm", "HsmArn", None, None)


@resources.register('hsm-hapg')
class PartitionGroup(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudhsm'
        enum_spec = ('list_hapgs', 'HapgList', None)
        detail_spec = ('describe_hapg', 'HapgArn', None, None)
        arn = id = 'HapgArn'
        name = 'HapgSerial'
        date = 'LastModifiedTimestamp'


@resources.register('hsm-client')
class HSMClient(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudhsm'
        enum_spec = ('list_luna_clients', 'ClientList', None)
        detail_spec = ('describe_luna_client', 'ClientArn', None, None)
        arn = id = 'ClientArn'
        name = 'Label'
