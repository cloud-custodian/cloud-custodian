# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import itertools

from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n import utils
import jmespath

from .core import Action


class ModifyVpcSecurityGroupsAction(Action):
    """Common action for modifying security groups on a vpc attached resources.

    Security groups for add or remove can be specified via group id or
    name. Group removal also supports symbolic names such as
    'matched', 'network-location' or 'all'. 'matched' uses the
    annotations/output of the 'security-group' filter
    filter. 'network-location' uses the annotations of the
    'network-location' interface filter for `SecurityGroupMismatch`.

    Note a vpc attached resource requires at least one security group,
    this action will use the sg specified in `isolation-group` to ensure
    resources always have at least one security-group.

    type: modify-security-groups
        add: []
        remove: [] | matched | network-location
        isolation-group: sg-xyz
        add-by-tag: {}

    :example:

    .. code-block:: yaml

            policies:
              - name: set-prod-security-groups
                resource: ec2
                filters:
                  - type: value
                    key: 'tag:env'
                    value: 'prod'
                actions:
                  - type: modify-security-groups
                    add: prod-default-sg
                    remove:
                      - launch-wizard-1
                      - launch-wizard-2
                    add-by-tag:
                      key: environment
                      values:
                        - production
    """
    schema_alias = True
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['modify-security-groups']},
            'add': {'oneOf': [
                {'type': 'string'},
                {'type': 'array', 'items': {
                    'type': 'string'}}]},
            'remove': {'oneOf': [
                {'type': 'array', 'items': {
                    'type': 'string'}},
                {'enum': [
                    'matched', 'network-location', 'all',
                    {'type': 'string'}]}]},
            'isolation-group': {'oneOf': [
                {'type': 'string'},
                {'type': 'array', 'items': {
                    'type': 'string'}}]},
            'add-by-tag': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'key': {'type': 'string'},
                    'values': {'type': 'array', 'items': {'type': 'string'}}
                },
                'required': ['key', 'values']
            }
        },
        'anyOf': [
            {'required': ['isolation-group', 'remove', 'type']},
            {'required': ['add', 'remove', 'type']},
            {'required': ['add', 'type']},
            {'required': ['add-by-tag', 'type']}]
    }

    SYMBOLIC_SGS = {'all', 'matched', 'network-location'}

    sg_expr = None
    vpc_expr = None

    def validate(self):
        sg_filter = self.manager.filter_registry.get('security-group')
        if not sg_filter or not sg_filter.RelatedIdsExpression:
            raise PolicyValidationError(self._format_error((
                "policy:{policy} resource:{resource_type} does "
                "not support {action_type} action")))
        if self.get_action_group_names():
            vpc_filter = self.manager.filter_registry.get('vpc')
            if not vpc_filter or not vpc_filter.RelatedIdsExpression:
                raise PolicyValidationError(self._format_error((
                    "policy:{policy} resource:{resource_type} does not support "
                    "security-group names only ids in action:{action_type}")))
            self.vpc_expr = utils.jmespath_compile(vpc_filter.RelatedIdsExpression)
        if self.sg_expr is None:
            self.sg_expr = utils.jmespath_compile(
                self.manager.filter_registry.get('security-group').RelatedIdsExpression)
        if 'all' in self._get_array('remove') and not self._get_array('isolation-group'):
            raise PolicyValidationError(self._format_error((
                "policy:{policy} use of action:{action_type} with "
                "remove: all requires specifying isolation-group")))
        return self

    def get_group_names(self, groups):
        names = []
        for g in groups:
            if g.startswith('sg-'):
                continue
            elif g in self.SYMBOLIC_SGS:
                continue
            names.append(g)
        return names

    def get_action_group_names(self):
        """Return all the security group names configured in this action."""
        return self.get_group_names(
            list(itertools.chain(
                *[self._get_array('add'),
                  self._get_array('remove'),
                  self._get_array('isolation-group')])))

    def _format_error(self, msg, **kw):
        return msg.format(
            policy=self.manager.ctx.policy.name,
            resource_type=self.manager.type,
            action_type=self.type,
            **kw)

    def _get_array(self, k):
        v = self.data.get(k, [])
        if isinstance(v, (str, bytes)):
            return [v]
        return v

    def get_groups_by_names(self, names):
        """Resolve security names to security groups resources."""
        if not names:
            return []
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        sgs = self.manager.retry(
            client.describe_security_groups,
            Filters=[{
                'Name': 'group-name', 'Values': names}]).get(
                    'SecurityGroups', [])

        unresolved = set(names)
        for s in sgs:
            if s['GroupName'] in unresolved:
                unresolved.remove(s['GroupName'])

        if unresolved:
            raise PolicyExecutionError(self._format_error(
                "policy:{policy} security groups not found "
                "requested: {names}, found: {groups}",
                names=list(unresolved), groups=[g['GroupId'] for g in sgs]))
        return sgs

    def get_groups_by_tag(self, key, values):
        """Get security groups that match tag values."""
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        sgs = self.manager.retry(
            client.describe_security_groups,
            Filters=[{
                'Name': 'tag:' + key, 'Values': values}]).get(
                    'SecurityGroups', [])
        return sgs

    def resolve_group_names(self, r, target_group_ids, groups):
        """Resolve any security group names to the corresponding group ids

        With the context of a given network attached resource.
        """
        names = self.get_group_names(target_group_ids)
        if not names:
            return target_group_ids

        target_group_ids = list(target_group_ids)
        vpc_id = self.vpc_expr.search(r)
        if not vpc_id:
            raise PolicyExecutionError(self._format_error(
                "policy:{policy} non vpc attached resource used "
                "with modify-security-group: {resource_id}",
                resource_id=r[self.manager.resource_type.id]))

        found = False
        for n in names:
            for g in groups:
                if g['GroupName'] == n and g['VpcId'] == vpc_id:
                    found = g['GroupId']
            if not found:
                raise PolicyExecutionError(self._format_error((
                    "policy:{policy} could not resolve sg:{name} for "
                    "resource:{resource_id} in vpc:{vpc}"),
                    name=n,
                    resource_id=r[self.manager.resource_type.id], vpc=vpc_id))
            target_group_ids.remove(n)
            target_group_ids.append(found)
        return target_group_ids

    def resolve_remove_symbols(self, r, target_group_ids, rgroups):
        """Resolve the resources security groups that need be modified.

        Specifically handles symbolic names that match annotations from policy filters
        for groups being removed.
        """
        if 'matched' in target_group_ids:
            return r.get('c7n:matched-security-groups', ())
        elif 'network-location' in target_group_ids:
            for reason in r.get('c7n:NetworkLocation', ()):
                if reason['reason'] == 'SecurityGroupMismatch':
                    return list(reason['security-groups'])
        elif 'all' in target_group_ids:
            return rgroups
        return target_group_ids

    def get_groups(self, resources):
        """Return lists of security groups to set on each resource

        For each input resource, parse the various add/remove/isolation-
        group/add-by-tag policies for 'modify-security-groups' to find the
        resulting set of VPC security groups to attach to that resource.

        Returns a list of lists containing the resulting VPC security groups
        that should end up on each resource passed in.

        :param resources: List of resources containing VPC Security Groups
        :return: List of lists of security groups per resource

        """
        resolved_groups = self.get_groups_by_names(self.get_action_group_names())
        return_groups = []

        tag = self._get_array('add-by-tag')
        if tag:
            tag_filtered_groups = self.get_groups_by_tag(tag['key'], tag['values'])
        else:
            tag_filtered_groups = []

        for idx, r in enumerate(resources):
            rgroups = self.sg_expr.search(r) or []
            add_groups = self.resolve_group_names(
                r, self._get_array('add'), resolved_groups)
            remove_groups = self.resolve_remove_symbols(
                r,
                self.resolve_group_names(
                    r, self._get_array('remove'), resolved_groups),
                rgroups)
            isolation_groups = self.resolve_group_names(
                r, self._get_array('isolation-group'), resolved_groups)

            for sg in tag_filtered_groups:
                if sg['VpcId'] == jmespath.search(
                    self.manager.filter_registry.get('vpc').RelatedIdsExpression, r):
                    add_groups.append(sg['GroupId'])

            for g in remove_groups:
                if g in rgroups:
                    rgroups.remove(g)
            for g in add_groups:
                if g not in rgroups:
                    rgroups.append(g)

            if not rgroups:
                rgroups = list(isolation_groups)

            if len(rgroups) > 5:
                raise PolicyExecutionError(self._format_error(
                    "policy:{policy} - the number of security groups exceeds 5. "
                    "groups: {rgroups}",
                    rgroups=rgroups))

            return_groups.append(rgroups)

        return return_groups
