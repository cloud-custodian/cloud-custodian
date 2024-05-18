# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.utils import local_session
from c7n.tags import RemoveTag, Tag, TagActionFilter
from c7n.filters.offhours import OffHour, OnHour


class GetCoreNetwork(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('networkmanager')

        def augment(r):
            # List tags for the Notebook-Instance & set as attribute
            tags = self.manager.retry(client.list_tags_for_resource,
                ResourceArn=r['CoreNetworkArn'])['TagList']
            r['Tags'] = tags
            return r

        # Describe notebook-instance & then list tags
        resources = super().augment(resources)
        return list(map(augment, resources))


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
        arn = id = 'CoreNetworkArn'
        name = 'CoreNetworkId'
        date = 'CreatedAt'
        config_type = cfn_type = 'AWS::NetworkManager::CoreNetwork'
        permissions_augment = ("networkmanager:ListTagsForResource",)

    source_mapping = {'describe': GetCoreNetwork, 'config': ConfigSource}


CoreNetwork.filter_registry.register('marked-for-op', TagActionFilter)
CoreNetwork.filter_registry.register('offhour', OffHour)
CoreNetwork.filter_registry.register('onhour', OnHour)


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
    permissions = ('networkmanager:DeleteTags',)

    def process_resource_set(self, client, resources, keys):
        mid = self.manager.resource_type.id
        for r in resources:
            try:
                client.untag_resource(ResourceArn=r[mid], TagKeys=keys)
            except client.exceptions.ResourceNotFoundException:
                continue
