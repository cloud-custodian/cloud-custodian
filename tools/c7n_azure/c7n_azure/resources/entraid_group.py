# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import requests

from c7n.filters import Filter

from c7n.utils import type_schema

from c7n_azure.provider import resources
from c7n_azure.graph_utils import (
    GraphResourceManager, GraphTypeInfo, GraphSource, EntraIDDiagnosticSettingsFilter
)

log = logging.getLogger('custodian.azure.entraid.group')


@resources.register('entraid-group')
class EntraIDGroup(GraphResourceManager):
    """EntraID Group resource for managing Azure AD groups.

    Supports filtering by group properties, membership analysis, and security monitoring.
    See Common EntraID Examples section for basic patterns.

    Available filters: value, member-count, owner-count, member-types, group-type

    Permissions: See Graph API Permissions Reference section.

    :example:

    Find groups without owners:

    .. code-block:: yaml

        policies:
          - name: groups-no-owners
            resource: azure.entraid-group
            filters:
              - type: owner-count
                count: 0
                op: equal
    """

    def __init__(self, ctx, data):
        super().__init__(ctx, data)
        # Use our custom GraphSource instead of the default source
        self.source = GraphSource(self)

    class resource_type(GraphTypeInfo):
        doc_groups = ['EntraID', 'Identity']
        enum_spec = ('groups', 'list', None)
        detail_spec = ('groups', 'get', 'id')
        id = 'id'
        name = 'displayName'
        date = 'createdDateTime'
        default_report_fields = (
            'displayName',
            'description',
            'mail',
            'groupTypes',
            'securityEnabled',
            'mailEnabled',
            'createdDateTime',
            'id'
        )
        permissions = ('Group.Read.All', 'GroupMember.Read.All')

    def get_graph_resources(self):
        """Get resources from Microsoft Graph API for use with GraphSource."""
        try:
            response = self.make_graph_request('groups')
            resources = response.get('value', [])

            log.debug(f"Retrieved {len(resources)} groups from Graph API")

            # Augment resources with additional computed fields
            resources = self.augment(resources)

            log.debug(f"Returning {len(resources)} groups after augmentation")
            return resources
        except requests.exceptions.RequestException as e:
            log.error(f"Error retrieving EntraID groups: {e}")
            if "Insufficient privileges" in str(e) or "403" in str(e):
                log.error(
                    "Insufficient privileges to read groups. "
                    "Required permissions: Group.Read.All"
                )
            return []

    def augment(self, resources):
        """Augment group resources with additional Graph API data"""
        try:
            # Enhance with additional properties
            for resource in resources:
                # Add computed fields for policy evaluation
                resource['c7n:IsSecurityGroup'] = self._is_security_group(resource)
                resource['c7n:IsDistributionGroup'] = self._is_distribution_group(resource)
                resource['c7n:IsDynamicGroup'] = self._is_dynamic_group(resource)
                resource['c7n:IsAdminGroup'] = self._is_admin_group(resource)

        except Exception as e:
            log.warning(f"Failed to augment EntraID groups: {e}")

        return resources

    def _is_security_group(self, group):
        """Determine if group is a security group"""
        return (
            group.get('securityEnabled', False) and
            not group.get('mailEnabled', False)
        )

    def _is_distribution_group(self, group):
        """Determine if group is a distribution group"""
        return group.get('mailEnabled', False)

    def _is_dynamic_group(self, group):
        """Determine if group uses dynamic membership"""
        group_types = group.get('groupTypes', [])
        return 'DynamicMembership' in group_types

    def _is_admin_group(self, group):
        """Determine if group has administrative privileges"""
        display_name = group.get('displayName', '').lower()
        admin_indicators = [
            'admin', 'administrator', 'global', 'privileged',
            'security', 'compliance', 'exchange', 'sharepoint'
        ]
        return any(indicator in display_name for indicator in admin_indicators)

    def get_group_member_count(self, group_id):
        """Get accurate member count for a group using Graph API.

        Required permission: GroupMember.Read.All
        """
        try:
            # Use $count parameter for efficient counting
            endpoint = f'groups/{group_id}/members/$count'
            response = self.make_graph_request(endpoint)

            # Response should be a plain number
            if isinstance(response, (int, str)):
                return int(response)
            else:
                log.warning(f"Unexpected response format for member count: {response}")
                return 0

        except requests.exceptions.RequestException as e:
            if "403" in str(e) or "Insufficient privileges" in str(e):
                log.warning(
                    f"Insufficient privileges to read member count for group {group_id}. "
                    "Required permission: GroupMember.Read.All"
                )

                return None  # Unknown member count
            else:
                log.error(f"Error getting member count for group {group_id}: {e}")
                return None

    def get_group_owner_count(self, group_id):
        """Get accurate owner count for a group using Graph API.

        Required permission: Group.Read.All
        """
        try:
            # Use $count parameter for efficient counting
            endpoint = f'groups/{group_id}/owners/$count'
            response = self.make_graph_request(endpoint)

            # Response should be a plain number
            if isinstance(response, (int, str)):
                return int(response)
            else:
                log.warning(f"Unexpected response format for owner count: {response}")
                return 0

        except requests.exceptions.RequestException as e:
            if "403" in str(e) or "Insufficient privileges" in str(e):
                log.warning(
                    f"Insufficient privileges to read owner count for group {group_id}. "
                    "Required permission: Group.Read.All"
                )

                return None  # Unknown owner count
            else:
                log.error(f"Error getting owner count for group {group_id}: {e}")
                return None

    def analyze_group_member_types(self, group_id):
        """Analyze group member types (internal vs external/guest users).

        Required permission: GroupMember.Read.All, User.Read.All
        """
        try:
            # Get group members with userType field explicitly requested

            endpoint = (
                f'groups/{group_id}/members?$select=id,displayName,'
                'userPrincipalName,userType'
            )
            response = self.make_graph_request(endpoint)
            members = response.get('value', [])

            has_external_members = False
            has_guest_members = False

            for member in members:
                # Only analyze users (not other groups or service principals)
                if member.get('@odata.type') == '#microsoft.graph.user':
                    user_type = member.get('userType', 'Member')
                    user_principal_name = member.get('userPrincipalName', '')

                    # Check if user is a guest
                    if user_type.lower() == 'guest':
                        has_guest_members = True

                    # Check if user is external (from different domain)
                    # External users typically have #EXT# in their UPN or are guests
                    if '#EXT#' in user_principal_name or user_type.lower() == 'guest':
                        has_external_members = True

            return {
                'has_external_members': has_external_members,
                'has_guest_members': has_guest_members,
                'total_members': len([
                    m for m in members
                    if m.get('@odata.type') == '#microsoft.graph.user'
                ])
            }
        except requests.exceptions.RequestException as e:
            if "403" in str(e) or "Insufficient privileges" in str(e):
                log.warning(
                    f"Insufficient privileges to analyze member types for group {group_id}. "
                    "Required permissions: GroupMember.Read.All, User.Read.All"
                )

                return None  # Unknown member types
            else:
                log.error(f"Error analyzing member types for group {group_id}: {e}")
                return None


@EntraIDGroup.filter_registry.register('member-count')
class MemberCountFilter(Filter):
    """Filter groups based on member count.

    Required permission: GroupMember.Read.All

    :example:

    Find groups with too many members:

    .. code-block:: yaml

        policies:
          - name: large-groups
            resource: azure.entraid-group
            filters:
              - type: member-count
                count: 100
                op: greater-than
    """

    schema = type_schema(
        'member-count',
        count={'type': 'number'},
        op={'type': 'string', 'enum': ['greater-than', 'less-than', 'equal']}
    )

    def process(self, resources, event=None):  # pylint: disable=unused-argument
        count_threshold = self.data.get('count', 0)
        op = self.data.get('op', 'greater-than')

        filtered = []
        for resource in resources:
            group_id = resource.get('id')
            if not group_id:

                log.warning(
                    f"Skipping group without ID: {resource.get('displayName', 'Unknown')}"
                )

                continue

            # Get actual member count via Graph API
            member_count = self.manager.get_group_member_count(group_id)

            if member_count is None:
                # Unknown member count (permission error or API failure)
                # Skip this group to avoid false results

                log.warning(
                    f"Could not determine member count for group "
                    f"{resource.get('displayName', group_id)}"
                )
                continue

            if op == 'greater-than' and member_count > count_threshold:
                filtered.append(resource)
            elif op == 'less-than' and member_count < count_threshold:
                filtered.append(resource)
            elif op == 'equal' and member_count == count_threshold:
                filtered.append(resource)

        return filtered


@EntraIDGroup.filter_registry.register('owner-count')
class OwnerCountFilter(Filter):
    """Filter groups based on owner count.

    Required permission: Group.Read.All

    :example:

    Find groups without owners:

    .. code-block:: yaml

        policies:
          - name: groups-no-owners
            resource: azure.entraid-group
            filters:
              - type: owner-count
                count: 0
                op: equal
    """

    schema = type_schema(
        'owner-count',
        count={'type': 'number'},
        op={'type': 'string', 'enum': ['greater-than', 'less-than', 'equal']}
    )

    def process(self, resources, event=None):  # pylint: disable=unused-argument
        count_threshold = self.data.get('count', 0)
        op = self.data.get('op', 'equal')

        filtered = []
        for resource in resources:
            group_id = resource.get('id')
            if not group_id:

                log.warning(
                    f"Skipping group without ID: {resource.get('displayName', 'Unknown')}"
                )

                continue

            # Get actual owner count via Graph API
            owner_count = self.manager.get_group_owner_count(group_id)

            if owner_count is None:
                # Unknown owner count (permission error or API failure)
                # Skip this group to avoid false results

                log.warning(
                    f"Could not determine owner count for group "
                    f"{resource.get('displayName', group_id)}"
                )
                continue

            if op == 'greater-than' and owner_count > count_threshold:
                filtered.append(resource)
            elif op == 'less-than' and owner_count < count_threshold:
                filtered.append(resource)
            elif op == 'equal' and owner_count == count_threshold:
                filtered.append(resource)

        return filtered


@EntraIDGroup.filter_registry.register('member-types')
class MemberTypesFilter(Filter):
    """Filter groups based on member types (internal vs external users).

    Required permissions: GroupMember.Read.All, User.Read.All

    :example:

    Find groups with external members:

    .. code-block:: yaml

        policies:
          - name: groups-external-members
            resource: azure.entraid-group
            filters:
              - type: member-types
                include-external: true
    """

    schema = type_schema('member-types',
                        **{
                            'include-external': {'type': 'boolean'},
                            'include-guests': {'type': 'boolean'},
                            'members-only': {'type': 'boolean'}
                        })

    def process(self, resources, event=None):  # pylint: disable=unused-argument
        include_external = self.data.get('include-external', False)
        include_guests = self.data.get('include-guests', False)

        filtered = []
        for resource in resources:
            group_id = resource.get('id')
            if not group_id:

                log.warning(
                    f"Skipping group without ID: {resource.get('displayName', 'Unknown')}"
                )

                continue

            # Get actual member type analysis via Graph API
            member_analysis = self.manager.analyze_group_member_types(group_id)

            if member_analysis is None:
                # Unknown member types (permission error or API failure)
                # Skip this group to avoid false results

                log.warning(
                    f"Could not analyze member types for group "
                    f"{resource.get('displayName', group_id)}"
                )

                continue

            has_external_members = member_analysis['has_external_members']
            has_guest_members = member_analysis['has_guest_members']

            should_include = True

            if include_external and not has_external_members:
                should_include = False
            elif not include_external and has_external_members:
                should_include = False

            if include_guests and not has_guest_members:
                should_include = False
            elif not include_guests and has_guest_members:
                should_include = False

            if should_include:
                filtered.append(resource)

        return filtered


@EntraIDGroup.filter_registry.register('group-type')
class GroupTypeFilter(Filter):
    """Filter groups by type (security, distribution, dynamic, etc.).

    :example:

    Find security groups:

    .. code-block:: yaml

        policies:
          - name: security-groups
            resource: azure.entraid-group
            filters:
              - type: group-type
                group-type: security

    :example:

    Find dynamic groups:

    .. code-block:: yaml

        policies:
          - name: dynamic-groups
            resource: azure.entraid-group
            filters:
              - type: group-type
                group-type: dynamic
    """

    schema = type_schema('group-type',
                        **{
                            'group-type': {
                                'type': 'string',
                                'enum': ['security', 'distribution',
                                        'dynamic', 'unified', 'admin']
                            }
                        })

    def process(self, resources, event=None):  # pylint: disable=unused-argument
        group_type = self.data.get('group-type', 'security')

        filtered = []
        for resource in resources:
            should_include = False

            if group_type == 'security' and resource.get('c7n:IsSecurityGroup', False):
                should_include = True
            elif group_type == 'distribution' and resource.get('c7n:IsDistributionGroup', False):
                should_include = True
            elif group_type == 'dynamic' and resource.get('c7n:IsDynamicGroup', False):
                should_include = True
            elif group_type == 'admin' and resource.get('c7n:IsAdminGroup', False):
                should_include = True
            elif group_type == 'unified':
                # Microsoft 365 Groups (formerly Office 365 Groups)
                group_types = resource.get('groupTypes', [])
                should_include = 'Unified' in group_types

            if should_include:
                filtered.append(resource)

        return filtered


# Register diagnostic settings filter for EntraID groups
EntraIDGroup.filter_registry.register('diagnostic-settings', EntraIDDiagnosticSettingsFilter)
