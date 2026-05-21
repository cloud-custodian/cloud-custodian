# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.utils import local_session, type_schema
from c7n_gcp.actions import MethodAction
from c7n_gcp.filters.iampolicy import IamPolicyFilter

_AUDIT_LOG_CONFIG_SCHEMA = {
    'type': 'object',
    'required': ['log-type'],
    'additionalProperties': False,
    'properties': {
        'log-type': {
            'type': 'string',
            'enum': ['ADMIN_READ', 'DATA_READ', 'DATA_WRITE'],
        },
        'exempted-members': {
            'type': 'array',
            'items': {'type': 'string'},
            'minItems': 1,
        },
    },
}

_AUDIT_CONFIG_SCHEMA = {
    'type': 'array',
    'minItems': 1,
    'items': {
        'type': 'object',
        'required': ['service', 'audit-log-configs'],
        'additionalProperties': False,
        'properties': {
            'service': {'type': 'string'},
            'audit-log-configs': {
                'type': 'array',
                'minItems': 1,
                'items': _AUDIT_LOG_CONFIG_SCHEMA,
            },
        },
    },
}


class SetIamPolicy(MethodAction):
    """ Sets IAM policy. Supports both role bindings and auditConfigs (Data Access audit logs).

        The action supports two lists for modifying the existing IAM policy: `add-bindings` and
        `remove-bindings`. The `add-bindings` records are merged with the existing bindings,
        hereby no changes are made if all the required bindings are already present in the
        applicable resource. The `remove-bindings` records are used to filter out the existing
        bindings, so the action will take no effect if there are no matches. For more information,
        please refer to the `_add_bindings` and `_remove_bindings` methods respectively.

        Considering a record added both to the `add-bindings` and `remove-bindings` lists,
        which though is not a recommended thing to do in general, the latter is designed to be a
        more restrictive one, so the record will be removed from the existing IAM bindings in the
        end.

        There following member types are available to work with:
        - allUsers,
        - allAuthenticatedUsers,
        - user,
        - group,
        - domain,
        - serviceAccount.

        The `add-audit-configs` and `remove-audit-configs` keys allow enabling, disabling,
        or adjusting Data Access audit logs (`ADMIN_READ`, `DATA_READ`, `DATA_WRITE`) and
        their `exemptedMembers`. When removing, if no `exempted-members` are specified the
        entire `log-type` entry is removed; if `exempted-members` are specified only those
        members are pruned. A service entry is dropped entirely when all its log-types are removed.

        Note the `resource` field in the examples that could be changed to another resource that
        has both `setIamPolicy` and `getIamPolicy` methods (such as gcp.spanner-database-instance).

        Example using exact values:

        .. code-block:: yaml

            policies:
              - name: gcp-spanner-instance-set-iam-policy
                resource: gcp.spanner-instance
                actions:
                  - type: set-iam-policy
                    add-bindings:
                      - members:
                          - user:user1@test.com
                          - user:user2@test.com
                        role: roles/owner
                      - members:
                          - user:user3@gmail.com
                        role: roles/viewer
                    remove-bindings:
                      - members:
                          - user:user4@test.com
                        role: roles/owner
                      - members:
                          - user:user5@gmail.com
                          - user:user6@gmail.com
                        role: roles/viewer

        Example using the ``iam-policy`` filter with value filter semantics and
        ``remove-bindings: matched`` for dry-run-safe pattern matching:

        .. code-block:: yaml

            policies:
              - name: remove-service-account-admin-permissions
                resource: gcp.project
                filters:
                  - type: iam-policy
                    user-role:
                      role:
                        op: glob
                        value: 'roles/*admin'
                        value_type: normalize
                      user:
                        op: glob
                        value: 'serviceAccount:*'
                actions:
                  - type: set-iam-policy
                    remove-bindings: matched

        Example enabling Data Access audit logs and adding an exempted member:

        .. code-block:: yaml

            policies:
              - name: enable-data-access-audit-logs
                resource: gcp.project
                actions:
                  - type: set-iam-policy
                    add-audit-configs:
                      - service: allServices
                        audit-log-configs:
                          - log-type: DATA_READ
                          - log-type: DATA_WRITE
                            exempted-members:
                              - user:admin@example.com

        Example removing a specific audit log type:

        .. code-block:: yaml

            policies:
              - name: remove-data-write-audit-log
                resource: gcp.project
                actions:
                  - type: set-iam-policy
                    remove-audit-configs:
                      - service: allServices
                        audit-log-configs:
                          - log-type: DATA_WRITE
        """
    schema = type_schema('set-iam-policy',
                         **{
                             'minProperties': 1,
                             'additionalProperties': False,
                             'add-bindings': {
                                 'type': 'array',
                                 'minItems': 1,
                                 'items': {'role': {'type': 'string'},
                                           'members': {'type': 'array',
                                                       'items': {
                                                           'type': 'string'},
                                                       'minItems': 1}}
                             },
                             'remove-bindings': {
                                 'oneOf': [
                                     {'enum': ['matched']},
                                     {
                                         'type': 'array',
                                         'minItems': 1,
                                         'items': {
                                             'role': {'type': 'string'},
                                             'members': {'oneOf': [
                                                 {'type': 'array',
                                                  'items': {'type': 'string'},
                                                  'minItems': 1},
                                                 {'enum': ['*']}]}}}
                                 ]
                             },
                             'add-audit-configs': _AUDIT_CONFIG_SCHEMA,
                             'remove-audit-configs': _AUDIT_CONFIG_SCHEMA,
                         })
    method_spec = {'op': 'setIamPolicy'}
    schema_alias = True

    def get_resource_params(self, model, resource):
        """
        Fetches the full existing IAM policy once via `_get_existing_policy`, then:
        - merges/removes bindings via `_add_bindings` / `_remove_bindings` /
          `_remove_matched_bindings`,
        - merges/removes auditConfigs via `_add_audit_configs` / `_remove_audit_configs`,
        - round-trips the policy `etag` to prevent lost-update races and `version` to
          preserve IAM Conditions support (version 3 policies),
        - assembles the final `setIamPolicy` body.

        :param model: the parameters that are defined in a resource manager
        :param resource: the resource the action is applied to
        """
        params = self._verb_arguments(resource)
        policy = self._get_existing_policy(model, resource)

        existing_bindings = policy.get('bindings', [])
        existing_audit_configs = policy.get('auditConfigs', [])

        add_bindings = self.data.get('add-bindings', [])
        remove_bindings = self.data.get('remove-bindings', [])
        add_audit_configs = self.data.get('add-audit-configs', [])
        remove_audit_configs = self.data.get('remove-audit-configs', [])

        bindings_to_set = self._add_bindings(existing_bindings, add_bindings)
        if remove_bindings == 'matched':
            matched_pairs = resource.get(IamPolicyFilter.annotation_key, [])
            bindings_to_set = self._remove_matched_bindings(bindings_to_set, matched_pairs)
        else:
            bindings_to_set = self._remove_bindings(bindings_to_set, remove_bindings)

        audit_configs_to_set = self._add_audit_configs(existing_audit_configs, add_audit_configs)
        audit_configs_to_set = self._remove_audit_configs(
            audit_configs_to_set, remove_audit_configs)

        new_policy = {}
        if bindings_to_set:
            new_policy['bindings'] = bindings_to_set
        if audit_configs_to_set:
            new_policy['auditConfigs'] = audit_configs_to_set
        if 'etag' in policy:
            new_policy['etag'] = policy['etag']
        if 'version' in policy:
            new_policy['version'] = policy['version']

        params['body'] = {'policy': new_policy}
        if add_audit_configs or remove_audit_configs:
            params['body']['updateMask'] = 'bindings,etag,auditConfigs'
        return params

    def _get_existing_policy(self, model, resource):
        """
        Calls the `getIamPolicy` method and returns the full policy dict.

        :param model: the same as in `get_resource_params`
        :param resource: the same as in `get_resource_params`
        """
        return local_session(self.manager.session_factory).client(
            self.manager.resource_type.service,
            self.manager.resource_type.version,
            model.component).execute_query(
            'getIamPolicy', verb_arguments=self._verb_arguments(resource))

    def _get_existing_bindings(self, model, resource):
        """
        Returns the existing `bindings` list from the current IAM policy.

        :param model: the same as in `get_resource_params`
        :param resource: the same as in `get_resource_params`
        """
        return self._get_existing_policy(model, resource).get('bindings', [])

    def _verb_arguments(self, resource):
        """
        Returns a dictionary passed when making the `getIamPolicy` and 'setIamPolicy' API calls.

        :param resource: the same as in `get_resource_params`
        """
        return {'resource': resource[self.manager.resource_type.id]}

    def _add_bindings(self, existing_bindings, bindings_to_add):
        """
        Converts the provided lists using `_get_roles_to_bindings_dict`, then iterates through
        them so that the returned list combines:
        - among the roles mentioned in a policy, the existing members merged with the ones to add
          so that there are no duplicates,
        - as for the other roles, all their members.

        The roles or members that are mentioned in the policy and already present
        in the existing bindings are simply ignored with no errors produced.

        An empty list could be returned only if both `existing_bindings` and `bindings_to_remove`
        are empty, the possibility of which is defined by the caller of the method.

        For additional information on how the method works, please refer to the tests
        (e.g. test_spanner).

        :param existing_bindings: a list of dictionaries containing the 'role' and 'members' keys
                                  taken from the resource the action is applied to
        :param bindings_to_add: a list of dictionaries containing the 'role' and 'members' keys
                                taken from the policy
        """
        bindings = []
        roles_to_existing_bindings = self._get_roles_to_bindings_dict(existing_bindings)
        roles_to_bindings_to_add = self._get_roles_to_bindings_dict(bindings_to_add)
        for role in roles_to_bindings_to_add:
            updated_members = dict(roles_to_bindings_to_add[role])
            if role in roles_to_existing_bindings:
                existing_members = roles_to_existing_bindings[role]['members']
                members_to_add = list(filter(lambda member: member not in existing_members,
                                             updated_members['members']))
                updated_members['members'] = existing_members + members_to_add
            bindings.append(updated_members)

        for role in roles_to_existing_bindings:
            if role not in roles_to_bindings_to_add:
                bindings.append(roles_to_existing_bindings[role])
        return bindings

    def _remove_bindings(self, existing_bindings, bindings_to_remove):
        """
        Converts the provided lists using `_get_roles_to_bindings_dict`, then iterates through
        them so that the returned list combines:
        - among the roles mentioned in a policy, only the members that are not marked for removal,
        - as for the other roles, all their members.

        The roles or members that are mentioned in the policy but are absent
        in the existing bindings are simply ignored with no errors produced.

        As can be observed, it is possible to have an empty list returned either if
        `existing_bindings` is already empty or `bindings_to_remove` filters everything out.

        In addition, a star wildcard could be used as the `members` key value (members: '*')
        in order to remove all members from a role.

        For additional information on how the method works, please refer to the tests
        (e.g. test_spanner).

        :param existing_bindings: a list of dictionaries containing the 'role' and 'members' keys
                                  taken from the resource the action is applied to
        :param bindings_to_remove: a list of dictionaries containing the 'role' and 'members' keys
                                   taken from the policy
        """
        bindings = []
        roles_to_existing_bindings = self._get_roles_to_bindings_dict(existing_bindings)
        roles_to_bindings_to_remove = self._get_roles_to_bindings_dict(bindings_to_remove)
        for role in roles_to_bindings_to_remove:
            if (role in roles_to_existing_bindings and
                    roles_to_bindings_to_remove[role]['members'] != '*'):
                updated_members = dict(roles_to_existing_bindings[role])
                members_to_remove = roles_to_bindings_to_remove[role]
                updated_members['members'] = list(filter(
                    lambda member: member not in members_to_remove['members'],
                    updated_members['members']))
                if len(updated_members['members']) > 0:
                    bindings.append(updated_members)

        for role in roles_to_existing_bindings:
            if role not in roles_to_bindings_to_remove:
                bindings.append(roles_to_existing_bindings[role])
        return bindings

    def _remove_matched_bindings(self, existing_bindings, matched_pairs):
        """Remove specific (role, member) pairs annotated by the iam-policy filter.

        Reads the list of ``{role, member}`` dicts stored by the ``iam-policy`` filter
        under ``c7n:matched-iam-bindings`` and removes exactly those pairs from
        ``existing_bindings``, leaving everything else intact.

        :param existing_bindings: list of ``{role, members}`` dicts from the resource
        :param matched_pairs: list of ``{role, member}`` dicts from the filter annotation
        """
        pairs_to_remove = {(p['role'], p['member']) for p in matched_pairs}
        bindings = []
        for binding in existing_bindings:
            updated_members = [
                m for m in binding['members']
                if (binding['role'], m) not in pairs_to_remove
            ]
            if updated_members:
                bindings.append({**binding, 'members': updated_members})
        return bindings

    def _add_audit_configs(self, existing, to_add):
        """Merge new auditConfig entries into the existing list.

        For each service in `to_add`:
        - If the service is not present in `existing`, it is added wholesale.
        - If the service already exists, its `auditLogConfigs` are merged by `logType`:
          - New log types are appended.
          - Existing log types have their `exemptedMembers` unioned (no duplicates).

        This method is idempotent: running it again with the same `to_add` produces no change.

        :param existing: list of auditConfig dicts from the current IAM policy
        :param to_add: list of auditConfig specs from the policy YAML
        """
        by_service = {e['service']: e for e in existing}

        for spec in to_add:
            service = spec['service']
            new_log_configs = spec.get('audit-log-configs', [])

            if service not in by_service:
                by_service[service] = {
                    'service': service,
                    'auditLogConfigs': [self._spec_to_log_config(lc) for lc in new_log_configs],
                }
            else:
                existing_entry = by_service[service]
                existing_by_type = {
                    lc['logType']: lc
                    for lc in existing_entry.get('auditLogConfigs', [])
                }
                for lc_spec in new_log_configs:
                    log_type = lc_spec['log-type']
                    new_members = lc_spec.get('exempted-members', [])
                    if log_type not in existing_by_type:
                        existing_by_type[log_type] = self._spec_to_log_config(lc_spec)
                    elif new_members:
                        existing_members = existing_by_type[log_type].get('exemptedMembers', [])
                        merged = list(dict.fromkeys(existing_members + new_members))
                        existing_by_type[log_type] = {'logType': log_type,
                                                       'exemptedMembers': merged}
                existing_entry['auditLogConfigs'] = list(existing_by_type.values())

        return list(by_service.values())

    def _remove_audit_configs(self, existing, to_remove):
        """Prune auditConfig entries from the existing list.

        For each service in `to_remove`:
        - If the service is not present in `existing`, it is skipped (no-op).
        - For each log type in the removal spec:
          - If no `exempted-members` are specified, the entire log type entry is removed.
          - If `exempted-members` are specified, only those members are removed from the
            `exemptedMembers` list; the log type itself is kept (even if exemptedMembers
            becomes empty, the logType remains enabled).
        - If removing log types empties a service's `auditLogConfigs`, that service entry
          is dropped entirely.

        :param existing: list of auditConfig dicts from the current IAM policy
        :param to_remove: list of auditConfig specs from the policy YAML
        """
        removals = {spec['service']: spec for spec in to_remove}
        result = []

        for entry in existing:
            service = entry['service']
            if service not in removals:
                result.append(entry)
                continue

            types_to_remove = {
                lc_spec['log-type']: lc_spec.get('exempted-members', [])
                for lc_spec in removals[service].get('audit-log-configs', [])
            }

            filtered_log_configs = []
            for lc in entry.get('auditLogConfigs', []):
                log_type = lc['logType']
                if log_type not in types_to_remove:
                    filtered_log_configs.append(lc)
                    continue
                members_to_remove = types_to_remove[log_type]
                if not members_to_remove:
                    continue
                remaining = [m for m in lc.get('exemptedMembers', []) if m not in members_to_remove]
                pruned = {'logType': log_type}
                if remaining:
                    pruned['exemptedMembers'] = remaining
                filtered_log_configs.append(pruned)

            if filtered_log_configs:
                result.append({'service': service, 'auditLogConfigs': filtered_log_configs})

        return result

    def _spec_to_log_config(self, spec):
        """Convert a policy YAML log-config spec to a GCP auditLogConfig dict."""
        lc = {'logType': spec['log-type']}
        if 'exempted-members' in spec:
            lc['exemptedMembers'] = list(spec['exempted-members'])
        return lc

    def _get_roles_to_bindings_dict(self, bindings_list):
        """
        Converts a given list to a dictionary, values under the 'role' key in elements of whose
        become keys in the resulting dictionary while the elements themselves become values
        associated with these keys.

        :param bindings_list: a list whose elements are expected to have the 'role' key
        """
        return {binding['role']: binding for binding in bindings_list}
