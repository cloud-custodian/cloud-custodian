# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import ClientError
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
import c7n.filters.vpc as net_filters
from c7n.actions import BaseAction
from c7n.utils import local_session, type_schema


class DescribeCloudHSMCluster(DescribeSource):

    def get_resources(self, resource_ids, cache=True):
        client = local_session(self.manager.session_factory).client('cloudhsmv2')
        return self.manager.retry(
            client.describe_clusters,
            Filters={
                'clusterIds': resource_ids}).get('Clusters', ())

    def augment(self, resources):
        for r in resources:
            r['Tags'] = r.pop('TagList', ())
        return resources


@resources.register('cloudhsm-cluster')
class CloudHSMCluster(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudhsmv2'
        arn_type = 'cluster'
        permission_prefix = arn_service = 'cloudhsm'
        enum_spec = ('describe_clusters', 'Clusters', None)
        id = name = 'ClusterId'
        universal_taggable = object()
        permissions_augment = ("cloudhsm:ListTags",)

    source_mapping = {
        'describe': DescribeCloudHSMCluster
    }


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

    def resources(self, query=None, augment=True):
        try:
            return super().resources(query, augment)
        except ClientError as e:
            # cloudhsm is not available for new accounts, use cloudhsmV2
            if 'service is unavailable' in str(e):
                return []
            raise


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
