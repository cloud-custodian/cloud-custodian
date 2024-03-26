# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .aws import AWS
from c7n.query import (
    QueryResourceManager, TypeInfo, DescribeSource, ConfigSource)
from c7n.filters.vpc import VpcFilter, SubnetFilter
from c7n.filters import ListItemFilter
from c7n.actions import BaseAction
from c7n.utils import local_session, type_schema
from .aws import shape_validate
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction


class FirewallDescribe(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        augmented_resources = []
        for r in resources:
            status = r.pop('FirewallStatus', {})
            r['Firewall']['UpdateToken'] = r['UpdateToken']
            ar = r.pop('Firewall')
            ar['FirewallStatus'] = status
            augmented_resources.append(ar)
        return augmented_resources


class FirewallConfig(ConfigSource):

    def load_resource(self, item):
        resource = super().load_resource(item)
        resource.update(resource.pop('Firewall'))
        return resource


@AWS.resources.register('firewall')
class NetworkFirewall(QueryResourceManager):
    """AWS Network Firewall

    https://docs.aws.amazon.com/network-firewall/latest/developerguide/what-is-aws-network-firewall.html
    """
    source_mapping = {
        'describe': FirewallDescribe,
        'config': FirewallConfig
    }

    class resource_type(TypeInfo):

        service = 'network-firewall'
        enum_spec = ('list_firewalls', 'Firewalls', None)
        arn = 'FirewallArn'
        arn_type = 'firewall'
        detail_spec = ('describe_firewall', 'FirewallArn', 'FirewallArn', '')
        id = name = 'FirewallName'
        cfn_type = config_type = 'AWS::NetworkFirewall::Firewall'
        metrics_namespace = 'AWS/NetworkFirewall'
        universal_taggable = object()
        permissions_augment = ("network-firewall:ListTagsForResource",)


@NetworkFirewall.filter_registry.register('vpc')
class FirewallVpcFilter(VpcFilter):

    RelatedIdsExpression = 'VpcId'


@NetworkFirewall.filter_registry.register('subnet')
class FirewallSubnetFilter(SubnetFilter):

    RelatedIdsExpression = 'SubnetMappings[].SubnetId'


@NetworkFirewall.action_registry.register('tag')
class TagNetworkFirewall(Tag):
    """Create tags on Network Firewalls

    :example:

    .. code-block:: yaml

        policies:
            - name: network-firewall-tag
              resource: aws.firewall
              actions:
                - type: tag
                  key: test
                  value: something
    """
    permissions = ('network-firewall:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        for r in resources:
            client.tag_resource(ResourceArn=r["FirewallArn"], Tags=new_tags)


@NetworkFirewall.action_registry.register('remove-tag')
class RemoveNetworkFirewall(RemoveTag):
    """Remove tags from a network firewall
    :example:

    .. code-block:: yaml

        policies:
            - name: network-firewall-remove-tag
              resource: aws.firewall
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('network-firewall:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(ResourceArn=r['FirewallArn'], TagKeys=tags)


NetworkFirewall.filter_registry.register('marked-for-op', TagActionFilter)


@NetworkFirewall.action_registry.register('mark-for-op')
class MarkNetworkFirewallForOp(TagDelayedAction):
    """Mark network firewall for future actions

    :example:

    .. code-block:: yaml

        policies:
          - name: network-firewall-tag-mark
            resource: aws.firewall
            filters:
              - "tag:delete": present
            actions:
              - type: mark-for-op
                op: delete
                days: 1
    """


@NetworkFirewall.filter_registry.register('logging-config')
class NetworkFirewallLogging(ListItemFilter):
    """Filter for network firewall to look at logging configuration

    The schema to supply to the attrs follows the schema here:
     https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/network-firewall/client/describe_logging_configuration.html

    :example:

    .. code-block:: yaml

            policies:
              - name: network-firewall-logging-configuration
                resource: firewall
                filters:
                  - type: logging-config
                    attrs:
                      - LogType: FLOW
    """
    schema = type_schema(
        'logging-config',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )
    permissions = ('network-firewall:DescribeLoggingConfiguration',)
    annotation_key = 'c7n:NetworkFirewall'

    def get_item_values(self, resource):
        client = local_session(self.manager.session_factory).client('network-firewall')
        resource[self.annotation_key] = client \
                .describe_logging_configuration(
                    FirewallArn=resource['FirewallArn'],
                    FirewallName=resource['FirewallName'])\
                .get('LoggingConfiguration', {}).get('LogDestinationConfigs', [])

        return resource.get(self.annotation_key)


@NetworkFirewall.action_registry.register('delete')
class DeleteNetworkFirewall(BaseAction):
    """Delete a network firewall

    :example:

    .. code-block:: yaml

        policies:
          - name: network-firewall-delete
            resource: aws.firewall
            actions:
              - type: delete
    """
    schema = type_schema('delete',
        force={'type': 'boolean', 'default': False})

    def get_permissions(self):
        permissions = ('network-firewall:DeleteFirewall',)
        if self.data.get('force'):
            permissions += (
                UpdateNetworkFirewallDeleteProtection.permissions +
                UpdateNetworkFirewallLoggingConfiguration.permissions
            )
        return permissions

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('network-firewall')
        if self.data.get('force', False):
            # To forcibly delete a network firewall, it needs 2 conditions:
            # 1. DeleteProtection needs to be false.
            # 2. There should be no logging destination configured.
            del_protection_updater = self.manager.action_registry['update-delete-protection'](
                {'type': 'update-delete-protection', 'state': False}, self.manager)
            del_protection_updater.process(resources)
            logging_updater = self.manager.action_registry['update-logging-config'](
                {'type': 'update-logging-config', 'enabled': False}, self.manager)
            logging_updater.process(resources)
        for r in resources:
            try:
                client.delete_firewall(
                    FirewallName=r['FirewallName'],
                    FirewallArn=r['FirewallArn']
                )
            except client.exceptions.ResourceNotFoundException:
                continue


@NetworkFirewall.action_registry.register('update-delete-protection')
class UpdateNetworkFirewallDeleteProtection(BaseAction):
    """Enable/disable network firewall delete protection."""

    permissions = ('network-firewall:UpdateFirewallDeleteProtection',)

    schema = type_schema(
        'update-delete-protection',
        state={'type': 'boolean'}
    )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('network-firewall')
        state = self.data.get('state', True)
        for r in resources:
            try:
                client.update_firewall_delete_protection(
                    FirewallName=r['FirewallName'],
                    FirewallArn=r['FirewallArn'],
                    DeleteProtection=state
                    )
            except client.exceptions.ResourceNotFoundException:
                continue


@NetworkFirewall.action_registry.register('update-logging-config')
class UpdateNetworkFirewallLoggingConfiguration(BaseAction):
    """Update network firewall logging configuration.

     https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/network-firewall/client/update_logging_configuration.html

    :example:

    .. code-block:: yaml

            policies:
              - name: set-network-firewall-logging
                resource: firewall
                actions:
                  - type: update-logging-config
                    enabled: True
                    LoggingConfiguration:
                      LogDestinationConfigs:
                        - LogDestination:
                            bucketName: c7n-firewall-logging
                          LogType: ALERT
                          LogDestinationType: S3

              - name: delete-network-firewall-logging
                resource: firewall
                actions:
                  - type: update-logging-config
                    enabled: False

    """

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['update-logging-config']},
            'enabled': {'type': 'boolean'},
            'LoggingConfiguration': {'type': 'object'}
        },
    }
    permissions = ('network-firewall:UpdateLoggingConfiguration',)
    shape = 'UpdateLoggingConfigurationRequest'
    service = 'network-firewall'

    def validate(self):
        cfg = dict(self.data)
        enabled = cfg.get('enabled')
        if enabled:
            cfg.pop('type')
            cfg.pop('enabled')
            return shape_validate(
              cfg,
              self.shape,
              self.service)

    # Base on AWS documentation:
    # You can perform only one of the following actions in any call to UpdateLoggingConfiguration:
    # Create a new log destination object by adding a single LogDestinationConfig array element
    #    to LogDestinationConfigs.
    # Delete a log destination object by removing a single LogDestinationConfig array element from
    #     LogDestinationConfigs.
    # Change the LogDestination setting in a single LogDestinationConfig array element.
    def process(self, resources):
        client = local_session(self.manager.session_factory).client('network-firewall')
        for r in resources:
            params = self.data.get('LoggingConfiguration')
            if self.data.get('enabled'):
                try:
                    client.update_logging_configuration(
                        FirewallName=r['FirewallName'],
                        FirewallArn=r['FirewallArn'],
                        LoggingConfiguration=params
                        )
                except client.exceptions.ResourceNotFoundException:
                    continue
            else:
                loggingConfigurations = client.describe_logging_configuration(
                    FirewallArn=r['FirewallArn'],
                    FirewallName=r['FirewallName'])\
                .get('LoggingConfiguration', {}).get('LogDestinationConfigs', [])
                while loggingConfigurations:
                    loggingConfigurations.pop()
                    try:
                        client.update_logging_configuration(
                            FirewallName=r['FirewallName'],
                            FirewallArn=r['FirewallArn'],
                            LoggingConfiguration={'LogDestinationConfigs': loggingConfigurations}
                        )
                    except client.exceptions.ResourceNotFoundException:
                        continue
