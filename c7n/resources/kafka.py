# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema

from .aws import shape_validate


@resources.register('kafka')
class Kafka(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'kafka'
        enum_spec = ('list_clusters', 'ClusterInfoList', None)
        arn = id = 'ClusterArn'
        name = 'ClusterName'
        date = 'CreationTime'
        filter_name = 'ClusterNameFilter'
        filter_type = 'scalar'
        universal_taggable = object()
        cfn_type = 'AWS::MSK::Cluster'

    def augment(self, resources):
        for r in resources:
            if 'Tags' not in r:
                continue
            tags = []
            for k, v in r['Tags'].items():
                tags.append({'Key': k, 'Value': v})
            r['Tags'] = tags
        return resources


@Kafka.filter_registry.register('security-group')
class KafkaSGFilter(SecurityGroupFilter):

    RelatedIdsExpression = "BrokerNodeGroupInfo.SecurityGroups[]"


@Kafka.filter_registry.register('subnet')
class KafkaSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "BrokerNodeGroupInfo.ClientSubnets[]"


@Kafka.action_registry.register('set-monitoring')
class SetMonitoring(Action):

    schema = type_schema(
        'set-monitoring',
        config={'type': 'object', 'minProperties': 1},
        required=('config',))

    shape = 'UpdateMonitoringRequest'
    permissions = ('kafka:UpdateClusterConfiguration',)

    def validate(self):
        attrs = dict(self.data.get('config', {}))
        attrs['ClusterArn'] = 'arn:'
        attrs['CurrentVersion'] = '123'
        shape_validate(attrs, self.shape, 'kafka')
        return super(SetMonitoring, self).validate()

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('kafka')
        for r in self.filter_resources(resources, 'State', ('ACTIVE',)):
            params = dict(self.data.get('config', {}))
            params['ClusterArn'] = r['ClusterArn']
            params['CurrentVersion'] = r['CurrentVersion']
            client.update_monitoring(**params)


@Kafka.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')
    permissions = ('kafka:DeleteCluster',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('kafka')

        for r in resources:
            try:
                client.delete_cluster(ClusterArn=r['ClusterArn'])
            except client.exceptions.NotFoundException:
                continue
