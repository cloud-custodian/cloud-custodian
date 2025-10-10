# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.manager import resources
from c7n.filters.kms import KmsRelatedFilter
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.utils import local_session, type_schema

from .aws import shape_validate
from c7n.filters import CrossAccountAccessFilter
import json


class DescribeKafka(DescribeSource):

    def augment(self, resources):
        for r in resources:
            # preserve backwards compat with extant list_clsuters api
            if 'Provisioned' in r:
                for k, v in r['Provisioned'].items():
                    # dont overwrite
                    if k in r:
                        continue
                    r[k] = v
            if 'Tags' not in r:
                continue
            tags = []
            for k, v in r['Tags'].items():
                tags.append({'Key': k, 'Value': v})
            r['Tags'] = tags
        return resources


@resources.register('kafka')
class Kafka(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'kafka'
        enum_spec = ('list_clusters_v2', 'ClusterInfoList', None)
        arn = id = 'ClusterArn'
        name = 'ClusterName'
        date = 'CreationTime'
        filter_name = 'ClusterNameFilter'
        filter_type = 'scalar'
        universal_taggable = object()
        cfn_type = config_type = 'AWS::MSK::Cluster'
        permissions_augment = ("kafka:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeKafka,
        'config': ConfigSource
    }


@Kafka.filter_registry.register('security-group')
class KafkaSGFilter(SecurityGroupFilter):

    RelatedIdsExpression = "BrokerNodeGroupInfo.SecurityGroups[]"


@Kafka.filter_registry.register('subnet')
class KafkaCompoundSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "compound"

    def process(self, resources, event=None):
        # kafka v2 has both serverless and provisioned resources which have two different
        # locations for their subnet info

        class ProvisionedSubnetFilter(SubnetFilter):
            RelatedIdsExpression = "Provisioned.BrokerNodeGroupInfo.ClientSubnets[]"

        class ServerlessSubnetFilter(SubnetFilter):
            RelatedIdsExpression = "Serverless.VpcConfigs[].SubnetIds[]"

        p = []
        s = []

        for r in resources:
            if r['ClusterType'] == 'PROVISIONED':
                p.append(r)
            if r['ClusterType'] == 'SERVERLESS':
                s.append(r)

        result = []
        for filtered, fil in ((p, ProvisionedSubnetFilter), (s, ServerlessSubnetFilter), ):
            f = fil(self.data, self.manager)
            # necessary to validate otherwise the filter wont work
            f.validate()
            result.extend(f.process(filtered, event))

        return result


@Kafka.filter_registry.register('kms-key')
class KafkaKmsFilter(KmsRelatedFilter):
    """

    Filter a kafka cluster's data-volume encryption by its associcated kms key
    and optionally the aliasname of the kms key by using 'c7n:AliasName'

    :example:

    .. code-block:: yaml

        policies:
          - name: kafka-kms-key-filter
            resource: kafka
            filters:
              - type: kms-key
                key: c7n:AliasName
                value: alias/aws/kafka
    """
    RelatedIdsExpression = 'Provisioned.EncryptionInfo.EncryptionAtRest.DataVolumeKMSKeyId'


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


@resources.register('kafka-config')
class KafkaClusterConfiguration(QueryResourceManager):
    """ Resource Manager for MSK Kafka Configuration.
    """

    class resource_type(TypeInfo):
        service = 'kafka'
        enum_spec = ('list_configurations', 'Configurations', None)
        name = 'Name'
        id = arn = 'Arn'
        date = 'CreationTime'
        permissions_augment = ("kafka:ListConfigurations",)


@KafkaClusterConfiguration.action_registry.register('delete')
class DeleteClusterConfiguration(Action):
    """Delete MSK Cluster Configuration.

    :example:

    .. code-block:: yaml

            policies:
              - name: msk-delete-cluster-configuration
                resource: aws.kafka-config
                actions:
                  - type: delete
    """
    schema = type_schema('delete')
    permissions = ('kafka:DeleteConfiguration',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('kafka')
        for r in resources:
            try:
                client.delete_configuration(Arn=r['Arn'])
            except client.exceptions.NotFoundException:
                continue


@Kafka.filter_registry.register('cross-account')
class KafkaCrossAccountAccessFilter(CrossAccountAccessFilter):
    """Filters Kafka clusters with cross-account permissions.

    Only applies to provisioned clusters, as serverless clusters do not support resource policies.
    """

    policy_annotation = "c7n:Policy"
    permissions = ("kafka:GetClusterPolicy", )

    def process(self, resources, event=None):
        # Only process provisioned clusters; serverless clusters do not support resource policies.
        provisioned = [r for r in resources if r.get('ClusterType') == 'PROVISIONED']
        return super(KafkaCrossAccountAccessFilter, self).process(provisioned, event)

    def get_resource_policy(self, r):
        client = local_session(self.manager.session_factory).client('kafka')
        resp = client.get_cluster_policy(ClusterArn=r['ClusterArn'])
        policy = json.loads(resp.get('Policy'))

        # Annotate for reference/debugging
        r[self.policy_annotation] = policy
        return policy
