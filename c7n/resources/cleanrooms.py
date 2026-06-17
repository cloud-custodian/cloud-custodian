# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.manager import resources
from c7n.query import (
    ChildResourceManager, QueryResourceManager, TypeInfo,
    DescribeWithResourceTags)


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
        date = 'updateTime'
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
        date = 'updateTime'
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
        date = 'updateTime'
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
        name = 'displayName'
        date = 'updateTime'
        permission_prefix = 'cleanrooms'
