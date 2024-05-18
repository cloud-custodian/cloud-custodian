# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.actions.core import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.utils import local_session, type_schema
from c7n.tags import RemoveTag, Tag


class GetCoreNetwork(DescribeSource):

    def augment(self, resources):

        resources = super().augment(resources)
        return resources


class DescribeGlobalNetwork(DescribeSource):

    def augment(self, resources):
        resources = super(DescribeGlobalNetwork, self).augment(resources)
        return resources


@resources.register('networkmanager-core-network')
class CoreNetwork(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'networkmanager'
        enum_spec = ('list_core_networks', 'CoreNetworks', None)
        detail_spec = (
            'get_core_network', 'CoreNetworkId',
            'CoreNetworkId', None)
        arn = 'CoreNetworkArn'
        id = 'CoreNetworkId'
        date = 'CreatedAt'
        config_type = cfn_type = 'AWS::NetworkManager::CoreNetwork'
        permissions_augment = ("networkmanager:ListTagsForResource",)
        universal_taggable = object()

    source_mapping = {'describe': GetCoreNetwork, 'config': ConfigSource}


@resources.register('networkmanager-global-network')
class GlobalNetwork(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'networkmanager'
        enum_spec = ('describe_global_networks', 'GlobalNetworks', None)
        # batch_detail_spec = (
        #    'describe_global_networks', 'GlobalNetworkIds',
        #    'GlobalNetworkId', 'GlobalNetworks', None)
        arn = 'GlobalNetworkArn'
        id = 'GlobalNetworkId'
        date = 'CreatedAt'
        config_type = cfn_type = 'AWS::NetworkManager::GlobalNetwork'
        permissions_augment = ("networkmanager:ListTagsForResource",)
        universal_taggable = object()

    source_mapping = {'describe': DescribeGlobalNetwork, 'config': ConfigSource}


@GlobalNetwork.action_registry.register('tag')
@CoreNetwork.action_registry.register('tag')
class TagNetwork(Tag):
    """Action to tag a networkmanager resource
    """
    permissions = ('networkmanager:TagResource',)

    def process_resource_set(self, client, resources, tags):
        mid = self.manager.resource_type.id
        for r in resources:
            try:
                client.tag_resource(ResourceArn=r[mid], Tags=tags)
            except client.exceptions.ResourceNotFoundException:
                continue


@GlobalNetwork.action_registry.register('remove-tag')
@CoreNetwork.action_registry.register('remove-tag')
class RemoveTagNetwork(RemoveTag):
    """Action to remove a tag from networkmanager resource
    """
    permissions = ('networkmanager:UntagResource',)

    def process_resource_set(self, client, resources, keys):
        mid = self.manager.resource_type.id
        for r in resources:
            try:
                client.untag_resource(ResourceArn=r[mid], TagKeys=keys)
            except client.exceptions.ResourceNotFoundException:
                continue


@CoreNetwork.action_registry.register('delete')
class DeleteCoreNetwork(BaseAction):
    """Action to delete a networkmanager core network
    """
    schema = type_schema('delete')
    permissions = ('networkmanager:DeleteCoreNetwork',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('networkmanager')

        for r in resources:
            try:
                client.delete_core_network(CoreNetworkId=r['CoreNetworkId'])
            except client.exceptions.ResourceNotFound:
                pass
