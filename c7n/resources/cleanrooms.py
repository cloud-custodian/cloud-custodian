# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.filters import ListItemFilter
from c7n.manager import resources
from c7n.query import (
    ChildResourceManager, QueryResourceManager, TypeInfo,
    DescribeWithResourceTags)
from c7n.utils import local_session, type_schema


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


@CleanRoomsCollaboration.filter_registry.register('members')
class CleanRoomsCollaborationMemberFilter(ListItemFilter):
    """Filter Clean Rooms collaborations on their members details.

    :example:

    .. code-block:: yaml

        policies:
          - name: cleanrooms-collaboration-with-members
            resource: cleanrooms-collaboration
            filters:
              - type: members
                attrs:
                  - type: value
                    key: status
                    value: ACTIVE
                  - type: value
                    key: abilities
                    op: intersect
                    value: [CAN_QUERY, CAN_RECEIVE]
    """

    schema = type_schema('members',
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"})

    annotation_key = 'c7n:Members'
    permissions = ('cleanrooms:ListMembers',)

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        data['key'] = f'"{self.annotation_key}"'

    def get_item_values(self, collaboration):
        if self.annotation_key in collaboration:
            return collaboration[self.annotation_key]
        client = local_session(self.manager.session_factory).client('cleanrooms')
        members = self.manager.retry(
            client.get_paginator('list_members').paginate,
            collaborationIdentifier=collaboration['id']
        ).build_full_result().get('memberSummaries', [])
        collaboration[self.annotation_key] = members
        return members


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
        # a member is identified by account id within its parent collaboration
        # and has no standalone arn;
        arn = False
        name = 'displayName'
        date = 'updateTime'
        permission_prefix = 'cleanrooms'
