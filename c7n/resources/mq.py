# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import Action
from c7n.filters.metrics import MetricsFilter
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
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


@MessageBroker.action_registry.register('delete')
class Delete(Action):
    """Delete a set of message brokers
    """

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
