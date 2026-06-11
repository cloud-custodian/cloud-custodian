# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import (
    ChildResourceManager, DescribeSource, QueryResourceManager, TypeInfo,
    DescribeWithResourceTags)
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import local_session


@resources.register('cleanrooms-collaboration')
class CleanRoomsCollaboration(QueryResourceManager):
    """AWS Clean Rooms Collaboration"""

    class resource_type(TypeInfo):
        service = 'cleanrooms'
        enum_spec = ('list_collaborations', 'collaborationList', None)
        detail_spec = (
            'get_collaboration', 'collaborationIdentifier', 'id', 'collaboration')
        id = 'id'
        arn = 'arn'
        name = 'name'
        date = 'createTime'
        cfn_type = 'AWS::CleanRooms::Collaboration'
        permission_prefix = 'cleanrooms'
        universal_taggable = object()

    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('cleanrooms-membership')
class CleanRoomsMembership(QueryResourceManager):
    """AWS Clean Rooms Membership"""

    class resource_type(TypeInfo):
        service = 'cleanrooms'
        enum_spec = ('list_memberships', 'membershipSummaries', None)
        detail_spec = (
            'get_membership', 'membershipIdentifier', 'id', 'membership')
        id = 'id'
        arn = 'arn'
        name = 'collaborationName'
        date = 'createTime'
        cfn_type = 'AWS::CleanRooms::Membership'
        permission_prefix = 'cleanrooms'
        universal_taggable = object()

    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('cleanrooms-configured-table')
class CleanRoomsConfiguredTable(QueryResourceManager):
    """AWS Clean Rooms Configured Table"""

    class resource_type(TypeInfo):
        service = 'cleanrooms'
        enum_spec = ('list_configured_tables', 'configuredTableSummaries', None)
        detail_spec = (
            'get_configured_table', 'configuredTableIdentifier', 'id',
            'configuredTable')
        id = 'id'
        arn = 'arn'
        name = 'name'
        date = 'createTime'
        cfn_type = 'AWS::CleanRooms::ConfiguredTable'
        permission_prefix = 'cleanrooms'
        universal_taggable = object()

    source_mapping = {'describe': DescribeWithResourceTags}


@resources.register('cleanrooms-collaboration-member')
class CleanRoomsCollaborationMember(ChildResourceManager):
    """AWS Clean Rooms Collaboration Member"""

    class resource_type(TypeInfo):
        service = 'cleanrooms'
        enum_spec = ('list_members', 'memberSummaries', None)
        parent_spec = ('cleanrooms-collaboration', 'collaborationIdentifier', True)
        id = 'accountId'
        arn = 'membershipArn'
        name = 'displayName'
        date = 'createTime'
        permission_prefix = 'cleanrooms'


class DescribeModelAlgorithm(DescribeSource):
    # Not supported by the resource groups tagging API
    def augment(self, resources):
        resources = super().augment(resources)
        client = local_session(self.manager.session_factory).client('cleanroomsml')
        for r in resources:
            tags = self.manager.retry(
                client.list_tags_for_resource,
                resourceArn=r['configuredModelAlgorithmArn']).get('tags', {})
            r['Tags'] = [{'Key': k, 'Value': v} for k, v in tags.items()]
        return resources


@resources.register('cleanroomsml-configured-model-algorithm')
class CleanRoomsMLConfiguredModelAlgorithm(QueryResourceManager):
    """AWS Clean Rooms ML Configured Model Algorithm"""

    class resource_type(TypeInfo):
        service = 'cleanroomsml'
        enum_spec = (
            'list_configured_model_algorithms', 'configuredModelAlgorithms', None)
        detail_spec = (
            'get_configured_model_algorithm', 'configuredModelAlgorithmArn',
            'configuredModelAlgorithmArn', None)
        id = arn = 'configuredModelAlgorithmArn'
        name = 'name'
        date = 'createTime'
        permission_prefix = 'cleanrooms-ml'

    source_mapping = {'describe': DescribeModelAlgorithm}


@CleanRoomsMLConfiguredModelAlgorithm.action_registry.register('tag')
class TagModelAlgorithm(Tag):
    permissions = ('cleanrooms-ml:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = {t['Key']: t['Value'] for t in new_tags}
        for r in resources:
            client.tag_resource(
                resourceArn=r['configuredModelAlgorithmArn'], tags=tags)


@CleanRoomsMLConfiguredModelAlgorithm.action_registry.register('remove-tag')
class RemoveTagModelAlgorithm(RemoveTag):
    permissions = ('cleanrooms-ml:UnTagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(
                resourceArn=r['configuredModelAlgorithmArn'], tagKeys=tags)


CleanRoomsMLConfiguredModelAlgorithm.action_registry.register(
    'mark-for-op', TagDelayedAction)
CleanRoomsMLConfiguredModelAlgorithm.filter_registry.register(
    'marked-for-op', TagActionFilter)
