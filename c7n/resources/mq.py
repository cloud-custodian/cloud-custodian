# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import ClientError
from c7n.actions import Action
from c7n.filters.metrics import MetricsFilter
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter, VpcFilter, DefaultVpcBase
from c7n.filters.kms import KmsRelatedFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema
from c7n.tags import RemoveTag, Tag, TagDelayedAction, TagActionFilter, universal_augment


@resources.register('message-broker')
class MessageBroker(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'mq'
        enum_spec = ('list_brokers', 'BrokerSummaries', None)
        detail_spec = (
            'describe_broker', 'BrokerId', 'BrokerId', None)
        cfn_type = 'AWS::AmazonMQ::Broker'
        id = 'BrokerId'
        arn = 'BrokerArn'
        name = 'BrokerName'
        dimension = 'Broker'
        metrics_namespace = 'AWS/AmazonMQ'

    permissions = ('mq:ListTags',)

    def augment(self, resources):
        super(MessageBroker, self).augment(resources)
        for r in resources:
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in r.get('Tags', {}).items()]
        return resources


@MessageBroker.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    """
    Filter a resource by its associcated kms key and optionally the aliasname
    of the kms key by using 'c7n:AliasName'

    :example:

    .. code-block:: yaml

        policies:
          - name: message-broker-kms-key-filter
            resource: message-broker
            filters:
              - type: kms-key
                key: c7n:AliasName
                value: "^(alias/aws/mq)"
                op: regex
    """

    RelatedIdsExpression = 'EncryptionOptions.KmsKeyId'


@MessageBroker.filter_registry.register('marked-for-op')
class MarkedForOp(TagActionFilter):

    permissions = ('mq:ListBrokers',)


@MessageBroker.filter_registry.register('subnet')
class MQSubnetFilter(SubnetFilter):

    RelatedIdsExpression = 'SubnetIds[]'


@MessageBroker.filter_registry.register('security-group')
class MQSGFilter(SecurityGroupFilter):

    RelatedIdsExpression = 'SecurityGroups[]'


@MessageBroker.filter_registry.register('metrics')
class MQMetrics(MetricsFilter):

    def get_dimensions(self, resource):
        # Fetching for Active broker instance only, https://amzn.to/2tLBhEB
        return [{'Name': self.model.dimension,
                 'Value': "{}-1".format(resource['BrokerName'])}]


@MessageBroker.filter_registry.register('vpc')
class VpcFilter(VpcFilter):
    """Filter a resource by its VPC id. Choose to select resources that are in that VPC or select
    resources that are not in that VPC using the 'op' field. Security group ID is used to get
    the VPC ID of a message broker, since DescribeMessageBrokers does not return a VPC ID.
    Since message brokers are exclusively launched in a single VPC, and their security groups
    all belong to this VPC, only the first security group id is needed to check the VPC
    ID of the message broker. Continue is used in the function if a client error occurs
    when trying to get a broker's vpc -- this will skip this broker, but still attempt to grab
    the vpc ids of the other brokers in the list.

    :example:

    .. code-block:: yaml

            policies:
              - name: mq-vpc-filters
                resource: message-broker
                filters: [{'type': 'vpc', 'key': 'VpcId', 'value': 'vpc-xxxxxxxxxxx', 'op': 'eq'}]
    """

    sg_vpc_dict = {}

    def get_related_ids(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        related_ids = set()
        for r in resources:
            try:
                sg_ids = r.get('SecurityGroups', [])
            except IndexError:
                continue
            vpc_id = self.sg_vpc_dict.get(sg_ids[0])
            if vpc_id:
                related_ids.add(vpc_id)
                continue
            try:
                response = client.describe_security_groups(
                    GroupIds=[sg_ids[0]],
                )
                vpc_id = response.get('SecurityGroups')[0].get('VpcId')
                related_ids.add(vpc_id)
                self.sg_vpc_dict[sg_ids[0]] = vpc_id
            except ClientError:
                continue
        return related_ids

    RelatedIdsExpression = "VpcId"


@MessageBroker.filter_registry.register('default-vpc')
class DefaultVpc(DefaultVpcBase):
    """Matches if an mq broker is in the default vpc

    :example:

    .. code-block:: yaml

            policies:
              - name: mq-default-filters
                resource: message-broker
                filters: [{'type': 'default-vpc'}]
    """

    schema = type_schema('default-vpc')

    def retrieve_vpc_id(self, mq):
        client = local_session(self.manager.session_factory).client('ec2')
        try:
            sg_ids = mq.get('SecurityGroups', [])
        except IndexError:
            return
        try:
            response = client.describe_security_groups(
                GroupIds=[sg_ids[0]],
            )
            vpc_id = response.get('SecurityGroups')[0].get('VpcId')
            return vpc_id
        except IndexError:
            return

    def __call__(self, mq):
        vpc_id = self.retrieve_vpc_id(mq)
        return vpc_id and self.match(vpc_id) or False


@MessageBroker.action_registry.register('delete')
class Delete(Action):
    """Delete a set of message brokers"""

    schema = type_schema('delete')
    permissions = ("mq:DeleteBroker",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('mq')
        for r in resources:
            try:
                client.delete_broker(BrokerId=r['BrokerId'])
            except client.exceptions.NotFoundException:
                continue


@MessageBroker.action_registry.register('tag')
class TagMessageBroker(Tag):
    """Action to create tag(s) on a mq

    :example:

    .. code-block:: yaml

            policies:
              - name: tag-mq
                resource: message-broker
                filters:
                  - "tag:target-tag": absent
                actions:
                  - type: tag
                    key: target-tag
                    value: target-tag-value
    """

    permissions = ('mq:CreateTags',)

    def process_resource_set(self, client, mq, new_tags):
        for r in mq:
            try:
                client.create_tags(
                    ResourceArn=r['BrokerArn'],
                    Tags={t['Key']: t['Value'] for t in new_tags})
            except client.exceptions.ResourceNotFound:
                continue


@MessageBroker.action_registry.register('remove-tag')
class UntagMessageBroker(RemoveTag):
    """Action to remove tag(s) on mq

    :example:

    .. code-block:: yaml

            policies:
              - name: mq-remove-tag
                resource: message-broker
                filters:
                  - "tag:OutdatedTag": present
                actions:
                  - type: remove-tag
                    tags: ["OutdatedTag"]
    """

    permissions = ('mq:DeleteTags',)

    def process_resource_set(self, client, mq, tags):
        for r in mq:
            try:
                client.delete_tags(ResourceArn=r['BrokerArn'], TagKeys=tags)
            except client.exceptions.ResourceNotFound:
                continue


@MessageBroker.action_registry.register('mark-for-op')
class MarkForOpMessageBroker(TagDelayedAction):
    """Action to specify an action to occur at a later date

    :example:

    .. code-block:: yaml

            policies:
              - name: mq-delete-unused
                resource: message-broker
                filters:
                  - "tag:custodian_cleanup": absent
                actions:
                  - type: mark-for-op
                    tag: custodian_cleanup
                    msg: "Unused mq"
                    op: delete
                    days: 7
    """


@resources.register('message-config')
class MessageConfig(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'mq'
        enum_spec = ('list_configurations', 'Configurations', None)
        cfn_type = 'AWS::AmazonMQ::Configuration'
        id = 'Id'
        arn = 'Arn'
        arn_type = 'configuration'
        name = 'Name'
        universal_taggable = object()

    augment = universal_augment
