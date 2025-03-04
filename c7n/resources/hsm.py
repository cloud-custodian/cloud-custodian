# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import ClientError
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
import c7n.filters.vpc as net_filters
from c7n.actions import BaseAction
from c7n.utils import local_session, type_schema
import c7n.filters.policystatement as polstmt_filter


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


class DescribeCloudHSMBackup(DescribeSource):

    def augment(self, resources):
        for r in resources:
            r['Tags'] = r.pop('TagList', ())
        return resources

    def resources(self, query):
        resources = self.query.filter(self.manager, **query)
        return [r for r in resources if r['BackupState'] != 'PENDING_DELETION']


@resources.register('cloudhsm-backup')
class CloudHSMBackup(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudhsmv2'
        arn_type = 'backup'
        permission_prefix = arn_service = 'cloudhsm'
        enum_spec = ('describe_backups', 'Backups', None)
        id = name = 'BackupId'
        universal_taggable = object()
        permissions_augment = ("cloudhsm:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeCloudHSMBackup
    }


@CloudHSMBackup.filter_registry.register('has-statement')
class HasStatementFilter(polstmt_filter.HasStatementFilter):
    """Find resources with matching resource policy statements.

    :example:

    .. code-block:: yaml

        policies:
            - name: cloudhsm-has-backup-poilcy
              resource: aws.cloudhsm-backup
              filters:
                - type: has-statement

            - name: cloudhsm-backup-policy-statement
              resource: aws.cloudhsm-backup
              filters:
                  - type: has-statement
                    statements:
                      - Action: "*"
                        Effect: "Allow"
    """

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.policy_attribute = 'c7n:Policy'

    def process(self, resources, event=None):
        resources = [self.policy_annotate(r) for r in resources if r['BackupState'] == 'READY']
        if not self.data.get('statement_ids', []) and not self.data.get('statements', []):
            return [r for r in resources if r.get(self.policy_attribute) != '{}']
        return super().process(resources, event)

    def policy_annotate(self, resource):
        client = local_session(self.manager.session_factory).client('cloudhsmv2')
        if self.policy_attribute in resource:
            return resource
        result = client.get_resource_policy(
                ResourceArn=resource['BackupArn']
            )
        resource[self.policy_attribute] = result['Policy']
        return resource

    def get_std_format_args(self, cloudhsm_backup):
        return {
            'backup_arn': cloudhsm_backup['BackupArn'],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region
        }
