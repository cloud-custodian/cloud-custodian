# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import functools
import logging
import re
import time

import requests

from c7n.filters import Filter
from c7n.utils import type_schema
from c7n_azure.constants import MSGRAPH_RESOURCE_ID
from c7n_azure.graph_utils import get_required_permissions_for_endpoint

log = logging.getLogger('custodian.azure.effective_access')

ALL_PRINCIPALS = '00000000-0000-0000-0000-000000000000'
GROUP_TYPES = ('Group', 'ForeignGroup')
LEAF_MEMBER_TYPES = ('#microsoft.graph.user', '#microsoft.graph.servicePrincipal')
EXPANDABLE_TYPES = ('Group',)
ANNOTATION = 'c7n:EffectiveAccess'
RETRY_STATUSES = (429, 503, 504)
MAX_RETRIES = 3
MAX_RETRY_WAIT = 60


@functools.lru_cache(maxsize=None)
def _compile(pattern):
    return re.compile('.*'.join(re.escape(part) for part in pattern.split('*')), re.IGNORECASE)


def action_matches(pattern, action):
    """True when a role action pattern covers a concrete action.

    Matching is case-insensitive and ``*`` matches any run of characters.
    """
    return _compile(pattern).fullmatch(action) is not None


def permission_grants(permission, data_action):
    """True when one role permission block grants the data action.

    ``notDataActions`` only cancels ``dataActions`` in the same block.
    """
    granted = any(action_matches(p, data_action) for p in permission.get('dataActions') or [])
    if not granted:
        return False
    return not any(
        action_matches(p, data_action) for p in permission.get('notDataActions') or [])


def permissions_grant(permissions, data_action):
    """True when any permission block of a role grants the data action."""
    return any(permission_grants(p, data_action) for p in permissions or [])


def deny_applies(deny, scope, principal_id, data_action):
    """True when a deny assignment removes the data action from the principal.

    A deny with a ``condition`` never applies, because the filter cannot
    evaluate conditions. A deny that names a group does not match the group's
    members.
    """
    props = deny['properties']
    if props.get('condition'):
        return False
    deny_scope = (props.get('scope') or '').lower()
    if props.get('doNotApplyToChildScopes') and deny_scope != scope.lower():
        return False
    if not permissions_grant(props.get('permissions'), data_action):
        return False
    pid = principal_id.lower()
    named = {(p.get('id') or '').lower() for p in props.get('principals') or []}
    if pid not in named and ALL_PRINCIPALS not in named:
        return False
    excluded = {(p.get('id') or '').lower() for p in props.get('excludePrincipals') or []}
    return pid not in excluded


def access_paths(assignments, role_defs, denies, scope, data_action):
    """Build one access path per role assignment that grants the data action.

    ``role_defs`` maps a lowercased role definition ID to a serialized role
    definition. A missing role raises ``KeyError``.
    """
    paths = []
    for assignment in assignments:
        props = assignment['properties']
        role = role_defs[props['roleDefinitionId'].lower()]
        if not permissions_grant(role['properties'].get('permissions'), data_action):
            continue
        if any(deny_applies(d, scope, props['principalId'], data_action) for d in denies):
            continue
        paths.append({
            'assignmentId': assignment['id'],
            'scope': props.get('scope'),
            'roleName': role['properties'].get('roleName'),
            'principalId': props['principalId'],
            'principalType': props.get('principalType'),
            'condition': props.get('condition'),
        })
    return paths


def classify(paths, approved_group_ids, approved_principal_ids):
    """Split paths into approved and unapproved.

    A path is approved when its principal ID is in ``approved_principal_ids``,
    or its principal is a group whose ID is in ``approved_group_ids``. A path
    without a principal type counts as a group for that test.
    """
    groups = {i.lower() for i in approved_group_ids}
    principals = {i.lower() for i in approved_principal_ids}
    approved, unapproved = [], []
    for path in paths:
        pid = path['principalId'].lower()
        if pid in principals or (path['principalType'] in GROUP_TYPES + (None,) and pid in groups):
            approved.append(path)
        else:
            unapproved.append(path)
    return approved, unapproved


def unapproved_members(members, approved_principal_ids):
    """List the users and service principals that are not approved.

    The function ignores Graph directory objects of any other type, including
    nested groups. Each entry carries the object ID and the Graph type.
    """
    approved = {i.lower() for i in approved_principal_ids}
    return [
        {'id': m['id'], 'type': m['@odata.type']}
        for m in members
        if m.get('@odata.type') in LEAF_MEMBER_TYPES and m['id'].lower() not in approved]


def members_approved(members, approved_principal_ids):
    """True when every user and service principal member is approved.

    An empty group has no members and counts as approved.
    """
    return not unapproved_members(members, approved_principal_ids)


def graph_get(url, headers, params):
    """GET a Graph URL, retrying throttled and unavailable responses.

    The function waits for ``Retry-After`` seconds when Graph sends the header
    and backs off 1, 2, then 4 seconds when it does not. It returns the last
    response after ``MAX_RETRIES`` retries.
    """
    for attempt in range(MAX_RETRIES + 1):
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code not in RETRY_STATUSES or attempt == MAX_RETRIES:
            return response
        try:
            wait = int(response.headers['Retry-After'])
        except (KeyError, ValueError):
            wait = 2 ** attempt
        wait = min(wait, MAX_RETRY_WAIT)
        log.warning('Microsoft Graph returned %s. Retrying in %ss.', response.status_code, wait)
        time.sleep(wait)


def transitive_members(session, group_id):
    """List a group's transitive members through Microsoft Graph v1.0.

    Documented at
    https://learn.microsoft.com/en-us/graph/api/group-list-transitivemembers
    """
    endpoint = 'groups/%s/transitiveMembers' % group_id
    permissions = get_required_permissions_for_endpoint(endpoint)
    graph = session.get_session_for_resource(MSGRAPH_RESOURCE_ID)
    graph._initialize_session()
    token = graph.credentials.get_token('https://graph.microsoft.com/.default')
    headers = {'Authorization': 'Bearer %s' % token.token}
    url = 'https://graph.microsoft.com/v1.0/' + endpoint
    params = {'$top': 999}
    members = []
    while url:
        response = graph_get(url, headers, params)
        if response.status_code == 403:
            log.error('Microsoft Graph denied %s. The executing identity needs %s.',
                      endpoint, ', '.join(permissions))
        response.raise_for_status()
        payload = response.json()
        members.extend(payload.get('value', []))
        url = payload.get('@odata.nextLink')
        params = None
    return members


class EffectiveAccess(Filter):
    """Filter resources where a principal outside an approved set holds a data action.

    The filter lists the role assignments at or above the resource scope,
    resolves each role, and keeps the assignments whose role grants
    ``data-action``. It drops access that an unconditional deny assignment
    blocks. A resource matches when any remaining principal fails the approval
    test. The filter annotates each resource with ``c7n:EffectiveAccess``,
    which lists the approved and unapproved access paths. With
    ``expand-groups``, each group path also lists its ``unapprovedMembers``.

    Limits:

    - The filter does not evaluate role assignment conditions. A conditional
      assignment counts as full access, and its path records the condition.
    - The filter does not subtract a deny assignment that carries a condition.
      It does not match a deny that names a group to the group's members.
    - The filter does not query Privileged Identity Management. It counts only
      assignments that the role assignment list returns, so eligible
      assignments never count.
    - The filter does not evaluate API key access (local authentication),
      which bypasses role assignments.
    - ``expand-groups`` expands ``Group`` principals only. It leaves a
      ``ForeignGroup`` unexpanded, so the filter reports it as unapproved
      unless ``approved-group-ids`` lists it.

    The executing identity needs ``Microsoft.Authorization/roleAssignments/read``,
    ``Microsoft.Authorization/roleDefinitions/read``, and
    ``Microsoft.Authorization/denyAssignments/read`` at the resource scope.
    ``expand-groups`` also needs the Microsoft Graph application permission
    ``GroupMember.ReadBasic.All``.

    :example:

    Find Azure OpenAI accounts where an unapproved principal can call chat
    completions.

    .. code-block:: yaml

        policies:
          - name: openai-chat-completions-unapproved-access
            resource: azure.cognitiveservice
            filters:
              - type: effective-access
                data-action: >-
                  Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action
                approved-group-ids:
                  - 00000000-0000-0000-0000-0000000000aa
                approved-principal-ids:
                  - 00000000-0000-0000-0000-0000000000bb

    :example:

    Treat a group as approved when every member is approved.

    .. code-block:: yaml

        policies:
          - name: openai-chat-completions-expanded
            resource: azure.cognitiveservice
            filters:
              - type: effective-access
                data-action: >-
                  Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action
                approved-principal-ids:
                  - 00000000-0000-0000-0000-0000000000bb
                expand-groups: true
    """

    schema = type_schema(
        'effective-access',
        required=['data-action'],
        **{
            'data-action': {'type': 'string', 'pattern': '^[^*]+$'},
            'approved-group-ids': {'type': 'array', 'items': {'type': 'string'}},
            'approved-principal-ids': {'type': 'array', 'items': {'type': 'string'}},
            'expand-groups': {'type': 'boolean'},
        })
    schema_alias = True
    permissions = (
        'Microsoft.Authorization/roleAssignments/read',
        'Microsoft.Authorization/roleDefinitions/read',
        'Microsoft.Authorization/denyAssignments/read',
    )

    def process(self, resources, event=None):
        session = self.manager.get_session()
        client = session.client('azure.mgmt.authorization.AuthorizationManagementClient')
        action = self.data['data-action']
        groups = self.data.get('approved-group-ids', [])
        principals = self.data.get('approved-principal-ids', [])
        role_defs = {}
        members = {}
        matched = []
        for resource in resources:
            scope = resource['id']
            assignments = [
                a.serialize(True)
                for a in client.role_assignments.list_for_scope(scope, filter='atScope()')]
            denies = [
                d.serialize(True)
                for d in client.deny_assignments.list_for_scope(scope, filter='atScope()')]
            for a in assignments:
                role_id = a['properties']['roleDefinitionId']
                if role_id.lower() not in role_defs:
                    role_defs[role_id.lower()] = client.role_definitions.get_by_id(
                        role_id).serialize(True)
            paths = access_paths(assignments, role_defs, denies, scope, action)
            approved, unapproved = classify(paths, groups, principals)
            if unapproved and self.data.get('expand-groups'):
                approved, unapproved = self.expand(session, approved, unapproved, members)
            resource[ANNOTATION] = {
                'data-action': action, 'approved': approved, 'unapproved': unapproved}
            if unapproved:
                matched.append(resource)
        return matched

    def expand(self, session, approved, unapproved, cache):
        principals = self.data.get('approved-principal-ids', [])
        remaining = []
        for path in unapproved:
            if path['principalType'] not in EXPANDABLE_TYPES:
                remaining.append(path)
                continue
            key = path['principalId'].lower()
            if key not in cache:
                cache[key] = transitive_members(session, path['principalId'])
            path['unapprovedMembers'] = unapproved_members(cache[key], principals)
            if not path['unapprovedMembers']:
                approved.append(path)
            else:
                remaining.append(path)
        return approved, remaining
