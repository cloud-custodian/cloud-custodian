# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy
from c7n.filters.core import Filter, ValueFilter

from c7n.utils import local_session, type_schema


class IamPolicyFilter(Filter):
    """
    Filters resources based on their IAM policy
    """

    annotation_key = 'c7n:matched-iam-bindings'

    value_filter_schema = copy.deepcopy(ValueFilter.schema)
    del value_filter_schema['required']

    user_role_schema = {
        'type': 'object',
        'additionalProperties': False,
        'required': ['user', 'role'],
        'properties': {
            'user': {
                'oneOf': [
                    {'type': 'string'},
                    value_filter_schema,
                ]
            },
            'role': {
                'oneOf': [
                    {'type': 'string'},
                    value_filter_schema,
                ]
            },
            'has': {'type': 'boolean'}
        }
    }

    schema = type_schema(
        'iam-policy',
        **{'doc': value_filter_schema,
        'user-role': user_role_schema})

    def get_client(self, session, model):
        return session.client(
            model.service, model.version, model.component)

    def _verb_arguments(self, resource):
        return {'resource': resource[self.manager.resource_type.id]}

    def process(self, resources, event=None):
        if 'doc' in self.data:
            try:
                resources = self.process_resources(resources)
            except TypeError:
                valueFilter = IamPolicyValueFilter(self.data['doc'], self.manager, "bucket")
                resources = valueFilter.process(resources)
        if 'user-role' in self.data:
            user_role = self.data['user-role']
            user_spec = user_role['user']
            role_spec = user_role['role']
            has = user_role.get('has', True)

            if isinstance(user_spec, dict) or isinstance(role_spec, dict):
                resources = self._filter_by_user_role_vf(resources, user_spec, role_spec, has)
            else:
                op = 'in' if has else 'not-in'
                userRolePairFilter = IamPolicyUserRolePairFilter(
                    {'key': user_spec, 'value': role_spec, 'op': op, 'value_type': 'swap'},
                    self.manager)
                resources = userRolePairFilter.process(resources)

        return resources

    def _filter_by_user_role_vf(self, resources, user_spec, role_spec, has):
        """Filter resources using value filter semantics on user and role.

        When either ``user`` or ``role`` in the ``user-role`` block is a
        value-filter sub-object (e.g. ``{op: glob, value: 'roles/*admin'}``),
        this method evaluates the filters against every binding in the resource's
        IAM policy and annotates matched resources with
        ``c7n:matched-iam-bindings`` — a list of ``{role, member}`` dicts for
        every binding pair that passed both filters.

        Resources are included when ``has: true`` (default) and at least one
        pair matched, or when ``has: false`` and no pairs matched.
        """
        model = self.manager.get_model()
        session = local_session(self.manager.session_factory)
        client = self.get_client(session, model)

        role_vf = None
        if isinstance(role_spec, dict):
            role_vf = ValueFilter(dict(role_spec, key='role'), self.manager)
            role_vf.annotate = False

        user_vf = None
        if isinstance(user_spec, dict):
            user_vf = ValueFilter(dict(user_spec, key='member'), self.manager)
            user_vf.annotate = False

        matched_resources = []
        for r in resources:
            iam_policy = client.execute_command('getIamPolicy', self._verb_arguments(r))
            matched_pairs = []

            for binding in iam_policy.get('bindings', []):
                if role_vf is not None:
                    role_matches = role_vf({'role': binding['role']})
                else:
                    role_matches = binding['role'] == role_spec

                if not role_matches:
                    continue

                for member in binding.get('members', []):
                    if user_vf is not None:
                        member_matches = user_vf({'member': member})
                    else:
                        member_matches = member == user_spec

                    if member_matches:
                        matched_pairs.append({'role': binding['role'], 'member': member})

            if has and matched_pairs:
                r[self.annotation_key] = r.get(self.annotation_key, []) + matched_pairs
                matched_resources.append(r)
            elif not has and not matched_pairs:
                matched_resources.append(r)

        return matched_resources

    def process_resources(self, resources):
        valueFilter = IamPolicyValueFilter(self.data['doc'], self.manager)
        resources = valueFilter.process(resources)
        return resources


class IamPolicyValueFilter(ValueFilter):
    """Generic value filter on resources' IAM policy bindings using jmespath

    :example:

    Filter all kms-cryptokeys accessible to all users
    or all authenticated users

    .. code-block :: yaml

       policies:
        - name: gcp-iam-policy-value
          resource: gcp.kms-cryptokey
          filters:
            - type: iam-policy
              doc:
                key: "bindings[*].members[]"
                op: intersect
                value: ["allUsers", "allAuthenticatedUsers"]
    """

    schema = type_schema('iam-policy', rinherit=ValueFilter.schema,)
#     permissions = 'GCP_SERVICE.GCP_RESOURCE.getIamPolicy',)

    def __init__(self, data, manager=None, identifier="resource"):
        super(IamPolicyValueFilter, self).__init__(data, manager)
        self.identifier = identifier

    def get_client(self, session, model):
        return session.client(
            model.service, model.version, model.component)

    def process(self, resources, event=None):
        model = self.manager.get_model()
        session = local_session(self.manager.session_factory)
        client = self.get_client(session, model)

        for r in resources:
            iam_policy = client.execute_command('getIamPolicy', self._verb_arguments(r))
            r["c7n:iamPolicy"] = iam_policy

        return super(IamPolicyValueFilter, self).process(resources)

    def __call__(self, r):
        return self.match(r['c7n:iamPolicy'])

    def _verb_arguments(self, resource):
        """
        Returns a dictionary passed when making the `getIamPolicy` and 'setIamPolicy' API calls.

        :param resource: the same as in `get_resource_params`
        """
        return {self.identifier: resource[self.manager.resource_type.id]}


class IamPolicyUserRolePairFilter(ValueFilter):
    """Filters resources based on specified user-role pairs.

    :example:

    Filter all projects where the user test123@gmail.com does not have the owner role

    .. code-block :: yaml

       policies:
        - name: gcp-iam-user-roles
          resource: gcp.project
          filters:
            - type: iam-policy
              user-role:
                user: "user:test123@gmail.com"
                has: false
                role: "roles/owner"
    """

    schema = type_schema('iam-user-roles', rinherit=ValueFilter.schema)
#     permissions = ('resourcemanager.projects.getIamPolicy',)

    def get_client(self, session, model):
        return session.client(
            model.service, model.version, model.component)

    def process(self, resources, event=None):
        model = self.manager.get_model()
        session = local_session(self.manager.session_factory)
        client = self.get_client(session, model)

        for r in resources:
            resource_key = 'projectId' if 'projectId' in r else 'name'
            iam_policy = client.execute_command('getIamPolicy', {"resource": r[resource_key]})
            r["c7n:iamPolicyUserRolePair"] = {}
            userToRolesMap = {}

            for b in iam_policy["bindings"]:
                role, members = b["role"], b["members"]
                for user in members:
                    if user in userToRolesMap:
                        userToRolesMap[user].append(role)
                    else:
                        userToRolesMap[user] = [role]
            for user, roles in userToRolesMap.items():
                r["c7n:iamPolicyUserRolePair"][user] = roles

        return super(IamPolicyUserRolePairFilter, self).process(resources)

    def __call__(self, r):
        return self.match(r["c7n:iamPolicyUserRolePair"])

    def _verb_arguments(self, resource, identifier="resource"):
        """
        Returns a dictionary passed when making the `getIamPolicy` and 'setIamPolicy' API calls.

        :param resource: the same as in `get_resource_params`
        """
        return {identifier: resource[self.manager.resource_type.id]}
