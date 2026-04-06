# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import type_schema
from c7n.exceptions import PolicyValidationError

from .core import ValueFilter, Filter
from .related import RelatedResourceFilter


class IamRoleFilter(RelatedResourceFilter):
    """Filter a resource by its associated IAM role attributes.

    This filter is available for resources that have IAM role attached
    (EC2 instance, Lambda function, ECS task definition etc.).

    :example:

    Find lambda functions using roles with specific tag:

    .. code-block:: yaml

    policies:
        - name: lambda-with-tagged-role
          resource: aws.lambda
          filters:
            - type: iam-role
              key: tag:Environment
              value: Production

    Find EC2 instances with roles that have specific permissions

    .. code-block:: yaml

    policies:
        - name: ec2-with-admin-role
          resources: aws.ec2
          filters:
            - type: iam-role
              key: RoleName
              value: ".*Admin.*"
              op: regex
    """

    schema = type_schema(
        'iam-role',
        rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}}
    )
    schema_alias = True
    RelatedResource = "c7n.resources.iam.Role"
    AnnotationKey = "matched-iam-role"


class IamRoleAlignment(Filter):
    """Determine alignment of IAM role attributes and resource attributes.

    This filter allows you to verify that a resource and its IAM role have
    matching attributes (like tags). Similar to network-location but for IAM roles.

    :Example:

    Find EC2 instances where the instance tag doesn't match the role tag:

    .. code-block:: yaml

      policies:
        - name: ec2-mismatched-role-tags
          resource: aws.ec2
          filters:
            - type: iam-role-alignment
              key: "tag:Environment"
              ignore:
                - "tag:Owner": "shared"

    Find lambda functions with mismatched cost center tags:

    .. code-block:: yaml

      policies:
        - name: lambda-role-mismatch
          resource: aws.lambda
          filters:
            - type: iam-role-alignment
              key: "tag:CostCenter"
              match: not-equal
      """

    schema = type_schema(
        'iam-role-alignment',
        required=['key'],
        **{'missing-ok': {
            'type': 'boolean',
            'default': False,
            'description': (
                "How to handle missing keys on elements, by default this causes"
                "resources to be considered not-equal")},
          'match': {'type': 'string', 'enum': ['equal', 'not-equal', 'in'],
                    'default': 'not-equal'},
          'key': {
              'type': 'string',
              'description': 'The attribute expression that should be matched on'},
          'ignore': {'type': 'array', 'items': {'type': 'object'}},
          'value': {'type': 'array', 'items': {'type': 'string'}}
        })
    schema_alias = True
    permissions = ('iam:GetRole', 'iam:ListRoleTags')

    def validate(self):
        rfilters = self.manager.filter_registry.keys()
        if 'iam-role' not in rfilters:
            raise PolicyValidationError(
                f"iam-role-alignment requires iam-role filter on {self.manager.data}")
        return self

    def process(self, resources, event=None):
        self.iam_role_filter = self.manager.filter_registry.get('iam-role')({}, self.manager)
        related_roles = self.iam_role_filter.get_related(resources)

        self.role_model = self.manager.get_resource_manager('iam-role').get_model()
        self.vf = self.manager.filter_registry.get('value')({}, self.manager)

        # filter options
        key = self.data.get('key')
        self.match = self.data.get('match', 'not-equal')
        self.missing_ok = self.data.get('missing-ok', False)

        results = []
        for r in resources:
            resource_roles = self.filter_ignored(
                [related_roles[rid] for rid in self.iam_role_filter.get_related_ids([r])
                 if rid in related_roles])
            # Skip resources with no roles left after filtering
            if not resource_roles:
                continue
            found = self.process_resource(r, resource_roles, key)
            if found:
                results.append(found)

        return results

    def filter_ignored(self, resources):
        """Filter out roles that match ignore conditions."""
        ignores = self.data.get('ignore', ())
        if not ignores:
            return resources

        filtered = []
        for r in resources:
            should_ignore = any(
                self.vf.get_resource_value(k, r) == v
                for ignore in ignores
                for k, v in ignore.items()
            )
            if not should_ignore:
                filtered.append(r)
        return filtered

    def process_resource(self, r, resource_roles, key):
        if self.match == 'in':
            return self.process_match_in(r, resource_roles, key)

        evaluation = []

        # Check IAM role attributes
        role_values = {
            rrole[self.role_model.id]: self.iam_role_filter.get_resource_value(key, rrole)
            for rrole in resource_roles}

        # Check for missing role attributes
        if not self.missing_ok and None in role_values.values():
            evaluation.append({
                'resson': 'RoleMissingAttribute',
                'key': key,
                'iam-role': role_values})

        role_space = set(filter(None, role_values.values()))

        # Check resource attributes
        r_value = self.vf.get_resource_value(key, r)

        # Check for missing resource attributes
        if not self.missing_ok and r_value is None:
            evaluation.append({
                'reason': 'ResourceMissingAttribute',
                'key': key,
                'resource': r_value})

        # Check for value mismatch (only if both resource and roles have values)
        if resource_roles and r_value is not None and role_space:
            mismatched_roles = {
                role_id: role_value
                for role_id, role_value in role_values.items()
                if role_value is not None and role_value != r_value
            }
            if mismatched_roles:
                evaluation.append({
                    'reason': 'AttributeMismatch',
                    'key': key,
                    'resource': r_value,
                    'iam-roles': mismatched_roles})

        # Return resources based on match type
        if self.match == 'not-equal' and evaluation:
            r['c7n:IamRoleAlignment'] = evaluation
            return r
        elif self.match == 'equal' and not evaluation:
            return r

        return None

    def process_match_in(self, r, resource_roles, key):
        allowed_values = set(self.data.get('value', []))

        # Check IAM roles - all role values must be in the allowed list
        role_values = {
            rrole[self.role_model.id]: self.iam_role_filter.get_resource_value(key, rrole)
            for rrole in resource_roles
        }

        # if missing-ok is False and any role is missing the key, fail
        if not self.missing_ok and None in role_values.values():
            return

        # Check if all non-None role values are in the allowed list
        role_space = set(filter(None, role_values.values()))
        if role_space and not role_space.issubset(allowed_values):
            return

        r_value = self.vf.get_resource_value(key, r)

        if not self.missing_ok and r_value is None:
            return

        if r_value is not None and r_value not in allowed_values:
            return
        return r
