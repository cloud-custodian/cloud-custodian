# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from collections import OrderedDict
import csv
import datetime
import functools
import json
import io
from datetime import timedelta
import itertools
import time
from xml.etree import ElementTree

from concurrent.futures import as_completed
from dateutil.tz import tzutc
from dateutil.parser import parse as parse_date

from botocore.exceptions import ClientError


from c7n.actions import BaseAction
from c7n.exceptions import PolicyValidationError
from c7n.filters import ValueFilter, Filter
from c7n.filters.multiattr import MultiAttrFilter
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import ConfigSource, QueryResourceManager, DescribeSource, TypeInfo
from c7n.resolver import ValuesFrom
from c7n.tags import TagActionFilter, TagDelayedAction, Tag, RemoveTag
from c7n.utils import (
    get_partition, local_session, type_schema, chunks, filter_empty, QueryParser,
    select_keys
)

from c7n.resources.aws import Arn
from c7n.resources.securityhub import OtherResourcePostFinding


class DescribeGroup(DescribeSource):

    def get_resources(self, resource_ids, cache=True):
        """For IAM Groups on events, resource ids are Group Names."""
        client = local_session(self.manager.session_factory).client('iam')
        resources = []
        for rid in resource_ids:
            try:
                result = self.manager.retry(client.get_group, GroupName=rid)
            except client.exceptions.NoSuchEntityException:
                continue
            group = result.pop('Group')
            group['c7n:Users'] = result['Users']
            resources.append(group)
        return resources


@resources.register('iam-group')
class Group(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'iam'
        arn_type = 'group'
        enum_spec = ('list_groups', 'Groups', None)
        id = name = 'GroupName'
        date = 'CreateDate'
        cfn_type = config_type = "AWS::IAM::Group"
        # Denotes this resource type exists across regions
        global_resource = True
        arn = 'Arn'

    source_mapping = {
        'describe': DescribeGroup,
        'config': ConfigSource
    }


class DescribeRole(DescribeSource):

    def get_resources(self, resource_ids, cache=True):
        client = local_session(self.manager.session_factory).client('iam')
        resources = []
        for rid in resource_ids:
            if rid.startswith('arn'):
                rid = Arn.parse(rid).resource
            try:
                result = self.manager.retry(client.get_role, RoleName=rid)
            except client.exceptions.NoSuchEntityException:
                continue
            resources.append(result.pop('Role'))
        return resources


@resources.register('iam-role')
class Role(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'iam'
        arn_type = 'role'
        enum_spec = ('list_roles', 'Roles', None)
        detail_spec = ('get_role', 'RoleName', 'RoleName', 'Role')
        id = name = 'RoleName'
        date = 'CreateDate'
        cfn_type = config_type = "AWS::IAM::Role"
        # Denotes this resource type exists across regions
        global_resource = True
        arn = 'Arn'

    source_mapping = {
        'describe': DescribeRole,
        'config': ConfigSource
    }


Role.action_registry.register('mark-for-op', TagDelayedAction)
Role.filter_registry.register('marked-for-op', TagActionFilter)


@Role.action_registry.register('post-finding')
class RolePostFinding(OtherResourcePostFinding):

    resource_type = 'AwsIamRole'

    def format_resource(self, r):
        envelope, payload = self.format_envelope(r)
        payload.update(self.filter_empty(
            select_keys(r, ['AssumeRolePolicyDocument', 'CreateDate',
                            'MaxSessionDuration', 'Path', 'RoleId',
                            'RoleName'])))
        payload['AssumeRolePolicyDocument'] = json.dumps(
            payload['AssumeRolePolicyDocument'])
        payload['CreateDate'] = payload['CreateDate'].isoformat()
        return envelope


@Role.action_registry.register('tag')
class RoleTag(Tag):
    """Tag an iam role."""

    permissions = ('iam:TagRole',)

    def process_resource_set(self, client, roles, tags):
        for role in roles:
            try:
                self.manager.retry(
                    client.tag_role, RoleName=role['RoleName'], Tags=tags)
            except client.exceptions.NoSuchEntityException:
                continue


@Role.action_registry.register('remove-tag')
class RoleRemoveTag(RemoveTag):
    """Remove tags from an iam role."""

    permissions = ('iam:UntagRole',)

    def process_resource_set(self, client, roles, tags):
        for role in roles:
            try:
                self.manager.retry(
                    client.untag_role, RoleName=role['RoleName'], TagKeys=tags)
            except client.exceptions.NoSuchEntityException:
                continue


class SetBoundary(BaseAction):
    """Set IAM Permission boundary on an IAM Role or User.

    A role or user can only have a single permission boundary set.
    """

    schema = type_schema(
        'set-boundary',
        state={'enum': ['present', 'absent']},
        policy={'type': 'string'})

    def validate(self):
        state = self.data.get('state', 'present') == 'present'
        if state and not self.data.get('policy'):
            raise PolicyValidationError("set-boundary requires policy arn")

    def process(self, resources):
        state = self.data.get('state', 'present') == 'present'
        client = self.manager.session_factory().client('iam')
        policy = self.data.get('policy')
        if policy and not policy.startswith('arn'):
            policy = 'arn:{}:iam::{}:policy/{}'.format(
                get_partition(self.manager.config.region),
                self.manager.account_id, policy)
        for r in resources:
            method, params = self.get_method(client, state, policy, r)
            try:
                self.manager.retry(method, **params)
            except client.exceptions.NoSuchEntityException:
                continue

    def get_method(self, client, state, policy, resource):
        raise NotImplementedError()


@Role.action_registry.register('set-boundary')
class RoleSetBoundary(SetBoundary):

    def get_permissions(self):
        if self.data.get('state', True):
            return ('iam:PutRolePermissionsBoundary',)
        return ('iam:DeleteRolePermissionsBoundary',)

    def get_method(self, client, state, policy, resource):
        if state:
            return client.put_role_permissions_boundary, {
                'RoleName': resource['RoleName'],
                'PermissionsBoundary': policy}
        else:
            return client.delete_role_permissions_boundary, {
                'RoleName': resource['RoleName']}


class DescribeUser(DescribeSource):

    def get_resources(self, resource_ids, cache=True):
        client = local_session(self.manager.session_factory).client('iam')
        results = []

        for r in resource_ids:
            try:
                results.append(client.get_user(UserName=r)['User'])
            except client.exceptions.NoSuchEntityException:
                continue
        return results


@resources.register('iam-user')
class User(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'iam'
        arn_type = 'user'
        detail_spec = ('get_user', 'UserName', 'UserName', 'User')
        enum_spec = ('list_users', 'Users', None)
        id = name = 'UserName'
        date = 'CreateDate'
        cfn_type = config_type = "AWS::IAM::User"
        # Denotes this resource type exists across regions
        global_resource = True
        arn = 'Arn'

    source_mapping = {
        'describe': DescribeUser,
        'config': ConfigSource
    }


@User.action_registry.register('tag')
class UserTag(Tag):
    """Tag an iam user."""

    permissions = ('iam:TagUser',)

    def process_resource_set(self, client, users, tags):
        for u in users:
            try:
                self.manager.retry(
                    client.tag_user, UserName=u['UserName'], Tags=tags)
            except client.exceptions.NoSuchEntityException:
                continue


@User.action_registry.register('remove-tag')
class UserRemoveTag(RemoveTag):
    """Remove tags from an iam user."""

    permissions = ('iam:UntagUser',)

    def process_resource_set(self, client, users, tags):
        for u in users:
            try:
                self.manager.retry(
                    client.untag_user, UserName=u['UserName'], TagKeys=tags)
            except client.exceptions.NoSuchEntityException:
                continue


User.action_registry.register('mark-for-op', TagDelayedAction)
User.filter_registry.register('marked-for-op', TagActionFilter)


Role.action_registry.register('mark-for-op', TagDelayedAction)
Role.filter_registry.register('marked-for-op', TagActionFilter)


@User.action_registry.register('set-groups')
class SetGroups(BaseAction):
    """Set a specific IAM user as added/removed from a group

    :example:

      .. code-block:: yaml

        - name: iam-user-add-remove
          resource: iam-user
          filters:
            - type: value
              key: UserName
              value: Bob
          actions:
            - type: set-groups
              state: remove
              group: Admin

    """
    schema = type_schema(
        'set-groups',
        state={'enum': ['add', 'remove']},
        group={'type': 'string'},
        required=['state', 'group']
    )

    permissions = ('iam:AddUserToGroup', 'iam:RemoveUserFromGroup',)

    def validate(self):
        if self.data.get('group') == '':
            raise PolicyValidationError('group cannot be empty on %s'
                % (self.manager.data))

    def process(self, resources):
        group_name = self.data['group']
        state = self.data['state']
        client = local_session(self.manager.session_factory).client('iam')
        op_map = {
            'add': client.add_user_to_group,
            'remove': client.remove_user_from_group
        }
        for r in resources:
            try:
                op_map[state](GroupName=group_name, UserName=r['UserName'])
            except client.exceptions.NoSuchEntityException:
                continue


@User.action_registry.register('set-boundary')
class UserSetBoundary(SetBoundary):

    def get_permissions(self):
        if self.data.get('state', True):
            return ('iam:PutUserPermissionsBoundary',)
        return ('iam:DeleteUserPermissionsBoundary',)

    def get_method(self, client, state, policy, resource):
        if state:
            return client.put_user_permissions_boundary, {
                'UserName': resource['UserName'],
                'PermissionsBoundary': policy}
        else:
            return client.delete_user_permissions_boundary, {
                'UserName': resource['UserName']}


class DescribePolicy(DescribeSource):

    def resources(self, query=None):
        qfilters = PolicyQueryParser.parse(self.manager.data.get('query', []))
        query = query or {}
        if qfilters:
            query = {t['Name']: t['Value'] for t in qfilters}
        return super(DescribePolicy, self).resources(query=query)

    def get_resources(self, resource_ids, cache=True):
        client = local_session(self.manager.session_factory).client('iam')
        results = []

        for r in resource_ids:
            try:
                results.append(client.get_policy(PolicyArn=r)['Policy'])
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchEntityException':
                    continue
        return results


@resources.register('iam-policy')
class Policy(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'iam'
        arn_type = 'policy'
        enum_spec = ('list_policies', 'Policies', None)
        id = 'PolicyId'
        name = 'PolicyName'
        date = 'CreateDate'
        cfn_type = config_type = "AWS::IAM::Policy"
        # Denotes this resource type exists across regions
        global_resource = True
        arn = 'Arn'

    source_mapping = {
        'describe': DescribePolicy,
        'config': ConfigSource
    }


class PolicyQueryParser(QueryParser):

    QuerySchema = {
        'Scope': ('All', 'AWS', 'Local'),
        'PolicyUsageFilter': ('PermissionsPolicy', 'PermissionsBoundary'),
        'PathPrefix': str,
        'OnlyAttached': bool
    }
    multi_value = False
    value_key = 'Value'


@resources.register('iam-profile')
class InstanceProfile(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'iam'
        arn_type = 'instance-profile'
        enum_spec = ('list_instance_profiles', 'InstanceProfiles', None)
        id = 'InstanceProfileId'
        name = 'InstanceProfileId'
        date = 'CreateDate'
        # Denotes this resource type exists across regions
        global_resource = True
        arn = 'Arn'


@resources.register('iam-certificate')
class ServerCertificate(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'iam'
        arn_type = 'server-certificate'
        enum_spec = ('list_server_certificates',
                     'ServerCertificateMetadataList',
                     None)
        id = 'ServerCertificateId'
        name = 'ServerCertificateName'
        date = 'Expiration'
        # Denotes this resource type exists across regions
        global_resource = True


@User.filter_registry.register('usage')
@Role.filter_registry.register('usage')
@Group.filter_registry.register('usage')
@Policy.filter_registry.register('usage')
class ServiceUsage(Filter):
    """Filter iam resources by their api/service usage.

    Note recent activity (last 4hrs) may not be shown, evaluation
    is against the last 365 days of data.

    Each service access record is evaluated against all specified
    attributes.  Attribute filters can be specified in short form k:v
    pairs or in long form as a value type filter.

    match-operator allows to specify how a resource is treated across
    service access record matches. 'any' means a single matching
    service record will return the policy resource as matching. 'all'
    means all service access records have to match.


    Find iam users that have not used any services in the last year

    :example:

    .. code-block:: yaml

      - name: usage-unused-users
        resource: iam-user
        filters:
          - type: usage
            match-operator: all
            LastAuthenticated: null

    Find iam users that have used dynamodb in last 30 days

    :example:

    .. code-block:: yaml

      - name: unused-users
        resource: iam-user
        filters:
          - type: usage
            ServiceNamespace: dynamodb
            TotalAuthenticatedEntities: 1
            LastAuthenticated:
              type: value
              value_type: age
              op: less-than
              value: 30
            match-operator: any

    https://aws.amazon.com/blogs/security/automate-analyzing-permissions-using-iam-access-advisor/

    """

    JOB_COMPLETE = 'COMPLETED'
    SERVICE_ATTR = {
        'ServiceName', 'ServiceNamespace', 'TotalAuthenticatedEntities',
        'LastAuthenticated', 'LastAuthenticatedEntity'}

    schema_alias = True
    schema_attr = {
        sa: {'oneOf': [
            {'type': 'string'},
            {'type': 'boolean'},
            {'type': 'number'},
            {'type': 'null'},
            {'$ref': '#/definitions/filters/value'}]}
        for sa in sorted(SERVICE_ATTR)}
    schema_attr['match-operator'] = {'enum': ['all', 'any']}
    schema_attr['poll-delay'] = {'type': 'number'}
    schema = type_schema(
        'usage',
        required=('match-operator',),
        **schema_attr)
    permissions = ('iam:GenerateServiceLastAccessedDetails',
                   'iam:GetServiceLastAccessedDetails')

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('iam')

        job_resource_map = {}
        for arn, r in zip(self.manager.get_arns(resources), resources):
            try:
                jid = self.manager.retry(
                    client.generate_service_last_accessed_details,
                    Arn=arn)['JobId']
                job_resource_map[jid] = r
            except client.exceptions.NoSuchEntityException:
                continue

        conf = dict(self.data)
        conf.pop('match-operator')
        saf = MultiAttrFilter(conf)
        saf.multi_attrs = self.SERVICE_ATTR

        results = []
        match_operator = self.data.get('match-operator', 'all')

        while job_resource_map:
            job_results_map = {}
            for jid, r in job_resource_map.items():
                result = self.manager.retry(
                    client.get_service_last_accessed_details, JobId=jid)
                if result['JobStatus'] != self.JOB_COMPLETE:
                    continue
                job_results_map[jid] = result['ServicesLastAccessed']

            for jid, saf_results in job_results_map.items():
                r = job_resource_map.pop(jid)
                saf_matches = saf.process(saf_results)
                if match_operator == 'all' and len(saf_matches) == len(saf_results):
                    results.append(r)
                elif match_operator != 'all' and saf_matches:
                    results.append(r)

            time.sleep(self.data.get('poll-delay', 2))

        return results


@User.filter_registry.register('check-permissions')
@Group.filter_registry.register('check-permissions')
@Role.filter_registry.register('check-permissions')
@Policy.filter_registry.register('check-permissions')
class CheckPermissions(Filter):
    """Check IAM permissions associated with a resource.

    :example:

    Find users that can create other users

    .. code-block:: yaml

        policies:
          - name: super-users
            resource: iam-user
            filters:
              - type: check-permissions
                match: allowed
                actions:
                 - iam:CreateUser

    By default permission boundaries are checked.
    """

    schema = type_schema(
        'check-permissions', **{
            'match': {'oneOf': [
                {'enum': ['allowed', 'denied']},
                {'$ref': '#/definitions/filters/valuekv'},
                {'$ref': '#/definitions/filters/value'}]},
            'boundaries': {'type': 'boolean'},
            'match-operator': {'enum': ['and', 'or']},
            'actions': {'type': 'array', 'items': {'type': 'string'}},
            'required': ('actions', 'match')})
    schema_alias = True
    policy_annotation = 'c7n:policy'
    eval_annotation = 'c7n:perm-matches'

    def get_permissions(self):
        if self.manager.type == 'iam-policy':
            return ('iam:SimulateCustomPolicy', 'iam:GetPolicyVersion')
        perms = ('iam:SimulatePrincipalPolicy', 'iam:GetPolicy', 'iam:GetPolicyVersion')
        if self.manager.type not in ('iam-user', 'iam-role',):
            # for simulating w/ permission boundaries
            perms += ('iam:GetRole',)
        return perms

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('iam')
        actions = self.data['actions']
        matcher = self.get_eval_matcher()
        operator = self.data.get('match-operator', 'and') == 'and' and all or any

        arn_resources = list(zip(self.get_iam_arns(resources), resources))
        self.initialize_boundaries(client, arn_resources)
        results = []
        eval_cache = {}
        for arn, r in arn_resources:
            if arn is None:
                continue
            if arn in eval_cache:
                evaluations = eval_cache[arn]
            else:
                evaluations = self.get_evaluations(client, arn, r, actions)
                eval_cache[arn] = evaluations
            matches = []
            matched = []
            for e in evaluations:
                match = matcher(e)
                if match:
                    matched.append(e)
                matches.append(match)
            if operator(matches):
                r[self.eval_annotation] = matched
                results.append(r)
        return results

    def initialize_boundaries(self, client, iam_resources):
        """For IAM boundaries we need to retrieve boundary policy content.
        """
        # boundaries aren't attached to these.
        if (self.manager.type in ('iam-policy', 'iam-group') or
                self.data.get('boundary', True) is False):
            return

        # if boundary attributes aren't directly on the resource, fetch
        # the iam role for the resource to get the boundary.
        if self.manager.type not in ('iam-role', 'iam-user'):
            iam_arns = {iam_arn for iam_arn, r in iam_resources if iam_arn is not None}
            roles = self.manager.get_resource_manager(
                'iam-role').get_resources(list(iam_arns), augment=False)
            boundary_iam_map = {
                r['Arn']: r.get('PermissionsBoundary', {}).get('PermissionsBoundaryArn')
                for r in roles}
            boundary_map = {}
            for iam_arn, r in iam_resources:
                boundary_map[self.manager.get_arns((r,))[0]] = boundary_iam_map.get(iam_arn)
        else:
            boundary_map = {
                resource_arn: r.get('PermissionsBoundary', {}).get('PermissionsBoundaryArn')
                for resource_arn, r in iam_resources}

        # fetch boundary policies text
        boundary_arns = set(boundary_map.values())
        if None in boundary_arns:
            boundary_arns.remove(None)
        policies = self.manager.get_resource_manager(
            'iam-policy').get_resources(list(boundary_arns))
        boundaries = {}
        for p in policies:
            boundaries[p['Arn']] = json.dumps(client.get_policy_version(
                PolicyArn=p['Arn'],
                VersionId=p['DefaultVersionId'])['PolicyVersion']['Document'])

        for resource_arn, boundary_arn in list(boundary_map.items()):
            if boundary_arn is None:
                continue
            boundary_map[resource_arn] = boundaries[boundary_arn]
        self.boundaries = boundary_map

    def get_iam_arns(self, resources):
        return self.manager.get_arns(resources)

    def get_evaluations(self, client, arn, r, actions):
        if self.manager.type == 'iam-policy':
            policy = r.get(self.policy_annotation)
            if policy is None:
                r['c7n:policy'] = policy = client.get_policy_version(
                    PolicyArn=r['Arn'],
                    VersionId=r['DefaultVersionId']).get('PolicyVersion', {})
            evaluations = self.manager.retry(
                client.simulate_custom_policy,
                PolicyInputList=[json.dumps(policy['Document'])],
                ActionNames=actions).get('EvaluationResults', ())
            return evaluations

        params = dict(PolicySourceArn=arn, ActionNames=actions)
        if self.boundaries:
            boundary_policy = self.boundaries.get(
                self.manager.get_arns([r])[0])
            if boundary_policy:
                params['PermissionsBoundaryPolicyInputList'] = [boundary_policy]

        evaluations = self.manager.retry(
            client.simulate_principal_policy, **params).get('EvaluationResults', ())
        return evaluations

    def get_eval_matcher(self):
        if isinstance(self.data['match'], str):
            if self.data['match'] == 'denied':
                values = ['explicitDeny', 'implicitDeny']
            else:
                values = ['allowed']
            vf = ValueFilter({'type': 'value', 'key':
                              'EvalDecision', 'value': values,
                              'op': 'in'})
        else:
            vf = ValueFilter(self.data['match'])
        vf.annotate = False
        return vf


class IamRoleUsage(Filter):

    def get_permissions(self):
        perms = list(itertools.chain(*[
            self.manager.get_resource_manager(m).get_permissions()
            for m in ['lambda', 'launch-config', 'ec2']]))
        perms.extend(['ecs:DescribeClusters', 'ecs:DescribeServices'])
        return perms

    def service_role_usage(self):
        results = set()
        results.update(self.scan_lambda_roles())
        results.update(self.scan_ecs_roles())
        results.update(self.collect_profile_roles())
        return results

    def instance_profile_usage(self):
        results = set()
        results.update(self.scan_asg_roles())
        results.update(self.scan_ec2_roles())
        return results

    def scan_lambda_roles(self):
        manager = self.manager.get_resource_manager('lambda')
        return [r['Role'] for r in manager.resources() if 'Role' in r]

    def scan_ecs_roles(self):
        results = []
        client = local_session(self.manager.session_factory).client('ecs')
        for cluster in client.describe_clusters()['clusters']:
            services = client.list_services(
                cluster=cluster['clusterName'])['serviceArns']
            if services:
                for service in client.describe_services(
                        cluster=cluster['clusterName'],
                        services=services)['services']:
                    if 'roleArn' in service:
                        results.append(service['roleArn'])
        return results

    def collect_profile_roles(self):
        # Collect iam roles attached to instance profiles of EC2/ASG resources
        profiles = set()
        profiles.update(self.scan_asg_roles())
        profiles.update(self.scan_ec2_roles())

        manager = self.manager.get_resource_manager('iam-profile')
        iprofiles = manager.resources()
        results = []
        for p in iprofiles:
            if p['InstanceProfileName'] not in profiles:
                continue
            for role in p.get('Roles', []):
                results.append(role['RoleName'])
        return results

    def scan_asg_roles(self):
        manager = self.manager.get_resource_manager('launch-config')
        return [r['IamInstanceProfile'] for r in manager.resources() if (
            'IamInstanceProfile' in r)]

    def scan_ec2_roles(self):
        manager = self.manager.get_resource_manager('ec2')
        results = []
        for e in manager.resources():
            # do not include instances that have been recently terminated
            if e['State']['Name'] == 'terminated':
                continue
            profile_arn = e.get('IamInstanceProfile', {}).get('Arn', None)
            if not profile_arn:
                continue
            # split arn to get the profile name
            results.append(profile_arn.split('/')[-1])
        return results


###################
#    IAM Roles    #
###################

@Role.filter_registry.register('used')
class UsedIamRole(IamRoleUsage):
    """Filter IAM roles that are either being used or not

    Checks for usage on EC2, Lambda, ECS only

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-role-in-use
            resource: iam-role
            filters:
              - type: used
                state: true
    """

    schema = type_schema(
        'used',
        state={'type': 'boolean'})

    def process(self, resources, event=None):
        roles = self.service_role_usage()
        if self.data.get('state', True):
            return [r for r in resources if (
                r['Arn'] in roles or r['RoleName'] in roles)]

        return [r for r in resources if (
            r['Arn'] not in roles and r['RoleName'] not in roles)]


@Role.filter_registry.register('unused')
class UnusedIamRole(IamRoleUsage):
    """Filter IAM roles that are either being used or not

    This filter has been deprecated. Please use the 'used' filter
    with the 'state' attribute to get unused iam roles

    Checks for usage on EC2, Lambda, ECS only

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-roles-not-in-use
            resource: iam-role
            filters:
              - type: used
                state: false
    """

    schema = type_schema('unused')

    def process(self, resources, event=None):
        return UsedIamRole({'state': False}, self.manager).process(resources)


@Role.filter_registry.register('cross-account')
class RoleCrossAccountAccess(CrossAccountAccessFilter):

    policy_attribute = 'AssumeRolePolicyDocument'
    permissions = ('iam:ListRoles',)

    schema = type_schema(
        'cross-account',
        # white list accounts
        whitelist_from=ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}})


@Role.filter_registry.register('has-inline-policy')
class IamRoleInlinePolicy(Filter):
    """Filter IAM roles that have an inline-policy attached
    True: Filter roles that have an inline-policy
    False: Filter roles that do not have an inline-policy

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-roles-with-inline-policies
            resource: iam-role
            filters:
              - type: has-inline-policy
                value: True
    """

    schema = type_schema('has-inline-policy', value={'type': 'boolean'})
    permissions = ('iam:ListRolePolicies',)

    def _inline_policies(self, client, resource):
        policies = client.list_role_policies(
            RoleName=resource['RoleName'])['PolicyNames']
        resource['c7n:InlinePolicies'] = policies
        return resource

    def process(self, resources, event=None):
        c = local_session(self.manager.session_factory).client('iam')
        res = []
        value = self.data.get('value', True)
        for r in resources:
            r = self._inline_policies(c, r)
            if len(r['c7n:InlinePolicies']) > 0 and value:
                res.append(r)
            if len(r['c7n:InlinePolicies']) == 0 and not value:
                res.append(r)
        return res


@Role.filter_registry.register('has-specific-managed-policy')
class SpecificIamRoleManagedPolicy(Filter):
    """Filter IAM roles that has a specific policy attached

    For example, if the user wants to check all roles with 'admin-policy':

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-roles-have-admin
            resource: iam-role
            filters:
              - type: has-specific-managed-policy
                value: admin-policy
    """

    schema = type_schema('has-specific-managed-policy', value={'type': 'string'})
    permissions = ('iam:ListAttachedRolePolicies',)

    def _managed_policies(self, client, resource):
        return [r['PolicyName'] for r in client.list_attached_role_policies(
            RoleName=resource['RoleName'])['AttachedPolicies']]

    def process(self, resources, event=None):
        c = local_session(self.manager.session_factory).client('iam')
        if self.data.get('value'):
            return [r for r in resources if self.data.get('value') in self._managed_policies(c, r)]
        return []


@Role.filter_registry.register('no-specific-managed-policy')
class NoSpecificIamRoleManagedPolicy(Filter):
    """Filter IAM roles that do not have a specific policy attached

    For example, if the user wants to check all roles without 'ip-restriction':

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-roles-no-ip-restriction
            resource: iam-role
            filters:
              - type: no-specific-managed-policy
                value: ip-restriction
    """

    schema = type_schema('no-specific-managed-policy', value={'type': 'string'})
    permissions = ('iam:ListAttachedRolePolicies',)

    def _managed_policies(self, client, resource):
        return [r['PolicyName'] for r in client.list_attached_role_policies(
            RoleName=resource['RoleName'])['AttachedPolicies']]

    def process(self, resources, event=None):
        c = local_session(self.manager.session_factory).client('iam')
        if self.data.get('value'):
            return [r for r in resources if not self.data.get('value') in
            self._managed_policies(c, r)]
        return []


@Role.action_registry.register('set-policy')
class SetPolicy(BaseAction):
    """Set a specific IAM policy as attached or detached on a role.

    You will identify the policy by its arn.

    Returns a list of roles modified by the action.

    For example, if you want to automatically attach a policy to all roles which don't have it...

    :example:

      .. code-block:: yaml

        - name: iam-attach-role-policy
          resource: iam-role
          filters:
            - type: no-specific-managed-policy
              value: my-iam-policy
          actions:
            - type: set-policy
              state: detached
              arn: "*"
            - type: set-policy
              state: attached
              arn: arn:aws:iam::123456789012:policy/my-iam-policy

    """
    schema = type_schema(
        'set-policy',
        state={'enum': ['attached', 'detached']},
        arn={'type': 'string'},
        required=['state', 'arn'])

    permissions = ('iam:AttachRolePolicy', 'iam:DetachRolePolicy',)

    def validate(self):
        if self.data.get('state') == 'attached' and self.data.get('arn') == "*":
            raise PolicyValidationError(
                '* operator is not supported for state: attached on %s' % (self.manager.data))

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iam')
        policy_arn = self.data['arn']
        state = self.data['state']
        for r in resources:
            if state == 'attached':
                client.attach_role_policy(
                    RoleName=r['RoleName'],
                    PolicyArn=policy_arn)
            elif state == 'detached' and policy_arn != "*":
                try:
                    client.detach_role_policy(
                        RoleName=r['RoleName'],
                        PolicyArn=policy_arn)
                except client.exceptions.NoSuchEntityException:
                    continue
            elif state == 'detached' and policy_arn == "*":
                try:
                    self.detach_all_policies(client, r)
                except client.exceptions.NoSuchEntityException:
                    continue

    def detach_all_policies(self, client, resource):
        attached_policy = client.list_attached_role_policies(RoleName=resource['RoleName'])
        policy_arns = [p.get('PolicyArn') for p in attached_policy['AttachedPolicies']]
        for parn in policy_arns:
            client.detach_role_policy(RoleName=resource['RoleName'], PolicyArn=parn)


@Role.action_registry.register('delete')
class RoleDelete(BaseAction):
    """Delete an IAM Role.

    For example, if you want to automatically delete an unused IAM role.

    :example:

      .. code-block:: yaml

        - name: iam-delete-unused-role
          resource: iam-role
          filters:
            - type: usage
              match-operator: all
              LastAuthenticated: null
          actions:
            - type: delete
              force: true

    """
    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = ('iam:DeleteRole',)

    def detach_inline_policies(self, client, r):
        policies = (self.manager.retry(
            client.list_role_policies, RoleName=r['RoleName'],
            ignore_err_codes=('NoSuchEntityException',)) or {}).get('PolicyNames', ())
        for p in policies:
            self.manager.retry(
                client.delete_role_policy,
                RoleName=r['RoleName'], PolicyName=p,
                ignore_err_codes=('NoSuchEntityException',))

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iam')
        error = None
        if self.data.get('force', False):
            policy_setter = self.manager.action_registry['set-policy'](
                {'state': 'detached', 'arn': '*'}, self.manager)
            policy_setter.process(resources)

        for r in resources:
            if self.data.get('force', False):
                self.detach_inline_policies(client, r)
            try:
                client.delete_role(RoleName=r['RoleName'])
            except client.exceptions.DeleteConflictException as e:
                self.log.warning(
                    "Role:%s cannot be deleted, set force to detach policy and delete"
                    % r['Arn'])
                error = e
            except (client.exceptions.NoSuchEntityException,
                    client.exceptions.UnmodifiableEntityException):
                continue
        if error:
            raise error


######################
#    IAM Policies    #
######################


@Policy.filter_registry.register('used')
class UsedIamPolicies(Filter):
    """Filter IAM policies that are being used
    (either attached to some roles or used as a permissions boundary).

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-policy-used
            resource: iam-policy
            filters:
              - type: used
    """

    schema = type_schema('used')
    permissions = ('iam:ListPolicies',)

    def process(self, resources, event=None):
        return [r for r in resources if
                r['AttachmentCount'] > 0 or r.get('PermissionsBoundaryUsageCount', 0) > 0]


@Policy.filter_registry.register('unused')
class UnusedIamPolicies(Filter):
    """Filter IAM policies that are not being used
    (neither attached to any roles nor used as a permissions boundary).

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-policy-unused
            resource: iam-policy
            filters:
              - type: unused
    """

    schema = type_schema('unused')
    permissions = ('iam:ListPolicies',)

    def process(self, resources, event=None):
        return [r for r in resources if
                r['AttachmentCount'] == 0 and r.get('PermissionsBoundaryUsageCount', 0) == 0]


@Policy.filter_registry.register('has-allow-all')
class AllowAllIamPolicies(Filter):
    """Check if IAM policy resource(s) have allow-all IAM policy statement block.

    This allows users to implement CIS AWS check 1.24 which states that no
    policy must exist with the following requirements.

    Policy must have 'Action' and Resource = '*' with 'Effect' = 'Allow'

    The policy will trigger on the following IAM policy (statement).
    For example:

    .. code-block:: json

      {
          "Version": "2012-10-17",
          "Statement": [{
              "Action": "*",
              "Resource": "*",
              "Effect": "Allow"
          }]
      }

    Additionally, the policy checks if the statement has no 'Condition' or
    'NotAction'.

    For example, if the user wants to check all used policies and filter on
    allow all:

    .. code-block:: yaml

     - name: iam-no-used-all-all-policy
       resource: iam-policy
       filters:
         - type: used
         - type: has-allow-all

    Note that scanning and getting all policies and all statements can take
    a while. Use it sparingly or combine it with filters such as 'used' as
    above.

    """
    schema = type_schema('has-allow-all')
    permissions = ('iam:ListPolicies', 'iam:ListPolicyVersions')

    def has_allow_all_policy(self, client, resource):
        statements = client.get_policy_version(
            PolicyArn=resource['Arn'],
            VersionId=resource['DefaultVersionId']
        )['PolicyVersion']['Document']['Statement']
        if isinstance(statements, dict):
            statements = [statements]

        for s in statements:
            if ('Condition' not in s and
                    'Action' in s and
                    isinstance(s['Action'], str) and
                    s['Action'] == "*" and
                    'Resource' in s and
                    isinstance(s['Resource'], str) and
                    s['Resource'] == "*" and
                    s['Effect'] == "Allow"):
                return True
        return False

    def process(self, resources, event=None):
        c = local_session(self.manager.session_factory).client('iam')
        results = [r for r in resources if self.has_allow_all_policy(c, r)]
        self.log.info(
            "%d of %d iam policies have allow all.",
            len(results), len(resources))
        return results


@Policy.action_registry.register('delete')
class PolicyDelete(BaseAction):
    """Delete an IAM Policy.

    For example, if you want to automatically delete all unused IAM policies.

    :example:

      .. code-block:: yaml

        - name: iam-delete-unused-policies
          resource: iam-policy
          filters:
            - type: unused
          actions:
            - delete

    """
    schema = type_schema('delete')
    permissions = ('iam:DeletePolicy',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iam')

        rcount = len(resources)
        resources = [r for r in resources if Arn.parse(r['Arn']).account_id != 'aws']
        if len(resources) != rcount:
            self.log.warning("Implicitly filtering AWS managed policies: %d -> %d",
                             rcount, len(resources))

        for r in resources:
            if r.get('DefaultVersionId', '') != 'v1':
                versions = [v['VersionId'] for v in client.list_policy_versions(
                    PolicyArn=r['Arn']).get('Versions') if not v.get('IsDefaultVersion')]
                for v in versions:
                    client.delete_policy_version(PolicyArn=r['Arn'], VersionId=v)
            client.delete_policy(PolicyArn=r['Arn'])


###############################
#    IAM Instance Profiles    #
###############################


@InstanceProfile.filter_registry.register('used')
class UsedInstanceProfiles(IamRoleUsage):
    """Filter IAM profiles that are being used.

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-instance-profiles-in-use
            resource: iam-profile
            filters:
              - type: used
    """

    schema = type_schema('used')

    def process(self, resources, event=None):
        results = []
        profiles = self.instance_profile_usage()
        for r in resources:
            if r['Arn'] in profiles or r['InstanceProfileName'] in profiles:
                results.append(r)
        self.log.info(
            "%d of %d instance profiles currently in use." % (
                len(results), len(resources)))
        return results


@InstanceProfile.filter_registry.register('unused')
class UnusedInstanceProfiles(IamRoleUsage):
    """Filter IAM profiles that are not being used

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-instance-profiles-not-in-use
            resource: iam-profile
            filters:
              - type: unused
    """

    schema = type_schema('unused')

    def process(self, resources, event=None):
        results = []
        profiles = self.instance_profile_usage()
        for r in resources:
            if (r['Arn'] not in profiles or r['InstanceProfileName'] not in profiles):
                results.append(r)
        self.log.info(
            "%d of %d instance profiles currently not in use." % (
                len(results), len(resources)))
        return results


###################
#    IAM Users    #
###################

class CredentialReport(Filter):
    """Use IAM Credential report to filter users.

    The IAM Credential report aggregates multiple pieces of
    information on iam users. This makes it highly efficient for
    querying multiple aspects of a user that would otherwise require
    per user api calls.

    https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_getting-report.html

    For example if we wanted to retrieve all users with mfa who have
    never used their password but have active access keys from the
    last month

    .. code-block:: yaml

     - name: iam-mfa-active-keys-no-login
       resource: iam-user
       filters:
         - type: credential
           key: mfa_active
           value: true
         - type: credential
           key: password_last_used
           value: absent
         - type: credential
           key: access_keys.last_used_date
           value_type: age
           value: 30
           op: less-than

    Credential Report Transforms

    We perform some default transformations from the raw
    credential report. Sub-objects (access_key_1, cert_2)
    are turned into array of dictionaries for matching
    purposes with their common prefixes stripped.
    N/A values are turned into None, TRUE/FALSE are turned
    into boolean values.

    """
    schema = type_schema(
        'credential',
        value_type={'$ref': '#/definitions/filters_common/value_types'},
        key={'type': 'string',
             'title': 'report key to search',
             'enum': [
                 'user',
                 'arn',
                 'user_creation_time',
                 'password_enabled',
                 'password_last_used',
                 'password_last_changed',
                 'password_next_rotation',
                 'mfa_active',
                 'access_keys',
                 'access_keys.active',
                 'access_keys.last_used_date',
                 'access_keys.last_used_region',
                 'access_keys.last_used_service',
                 'access_keys.last_rotated',
                 'certs',
                 'certs.active',
                 'certs.last_rotated',
             ]},
        value={'$ref': '#/definitions/filters_common/value'},
        op={'$ref': '#/definitions/filters_common/comparison_operators'},
        report_generate={
            'title': 'Generate a report if none is present.',
            'default': True,
            'type': 'boolean'},
        report_delay={
            'title': 'Number of seconds to wait for report generation.',
            'default': 10,
            'type': 'number'},
        report_max_age={
            'title': 'Number of seconds to consider a report valid.',
            'default': 60 * 60 * 24,
            'type': 'number'})

    list_sub_objects = (
        ('access_key_1_', 'access_keys'),
        ('access_key_2_', 'access_keys'),
        ('cert_1_', 'certs'),
        ('cert_2_', 'certs'))

    # for access keys only
    matched_annotation_key = 'c7n:matched-keys'

    permissions = ('iam:GenerateCredentialReport',
                   'iam:GetCredentialReport')

    def get_value_or_schema_default(self, k):
        if k in self.data:
            return self.data[k]
        return self.schema['properties'][k]['default']

    def get_credential_report(self):
        report = self.manager._cache.get('iam-credential-report')
        if report:
            return report
        data = self.fetch_credential_report()
        report = {}
        if isinstance(data, bytes):
            reader = csv.reader(io.StringIO(data.decode('utf-8')))
        else:
            reader = csv.reader(io.StringIO(data))
        headers = next(reader)
        for line in reader:
            info = dict(zip(headers, line))
            report[info['user']] = self.process_user_record(info)
        self.manager._cache.save('iam-credential-report', report)
        return report

    @classmethod
    def process_user_record(cls, info):
        """Type convert the csv record, modifies in place."""
        keys = list(info.keys())
        # Value conversion
        for k in keys:
            v = info[k]
            if v in ('N/A', 'no_information'):
                info[k] = None
            elif v == 'false':
                info[k] = False
            elif v == 'true':
                info[k] = True
        # Object conversion
        for p, t in cls.list_sub_objects:
            obj = dict([(k[len(p):], info.pop(k))
                        for k in keys if k.startswith(p)])
            if obj.get('active', False) or obj.get('last_rotated', False):
                info.setdefault(t, []).append(obj)
        return info

    def fetch_credential_report(self):
        client = local_session(self.manager.session_factory).client('iam')
        try:
            report = client.get_credential_report()
        except ClientError as e:
            if e.response['Error']['Code'] != 'ReportNotPresent':
                raise
            report = None
        if report:
            threshold = datetime.datetime.now(tz=tzutc()) - timedelta(
                seconds=self.get_value_or_schema_default(
                    'report_max_age'))
            if not report['GeneratedTime'].tzinfo:
                threshold = threshold.replace(tzinfo=None)
            if report['GeneratedTime'] < threshold:
                report = None
        if report is None:
            if not self.get_value_or_schema_default('report_generate'):
                raise ValueError("Credential Report Not Present")
            client.generate_credential_report()
            time.sleep(self.get_value_or_schema_default('report_delay'))
            report = client.get_credential_report()
        return report['Content']

    def process(self, resources, event=None):
        if '.' in self.data['key']:
            self.matcher_config = dict(self.data)
            self.matcher_config['key'] = self.data['key'].split('.', 1)[1]
        return []

    def match(self, resource, info):
        if info is None:
            return False
        k = self.data.get('key')
        if '.' not in k:
            vf = ValueFilter(self.data)
            vf.annotate = False
            return vf(info)

        # access key matching
        prefix, sk = k.split('.', 1)
        vf = ValueFilter(self.matcher_config)
        vf.annotate = False

        # annotation merging with previous respecting block operators
        k_matched = []
        for v in info.get(prefix, ()):
            if vf.match(v):
                k_matched.append(v)

        for k in k_matched:
            k['c7n:match-type'] = 'credential'

        self.merge_annotation(resource, self.matched_annotation_key, k_matched)
        return bool(k_matched)


@User.filter_registry.register('credential')
class UserCredentialReport(CredentialReport):

    def process(self, resources, event=None):
        super(UserCredentialReport, self).process(resources, event)
        report = self.get_credential_report()
        if report is None:
            return []
        results = []
        for r in resources:
            info = report.get(r['UserName'])
            if self.match(r, info):
                r['c7n:credential-report'] = info
                results.append(r)
        return results


@User.filter_registry.register('has-inline-policy')
class IamUserInlinePolicy(Filter):
    """
        Filter IAM users that have an inline-policy attached

        True: Filter users that have an inline-policy
        False: Filter users that do not have an inline-policy
    """

    schema = type_schema('has-inline-policy', value={'type': 'boolean'})
    permissions = ('iam:ListUserPolicies',)

    def _inline_policies(self, client, resource):
        resource['c7n:InlinePolicies'] = client.list_user_policies(
            UserName=resource['UserName'])['PolicyNames']
        return resource

    def process(self, resources, event=None):
        c = local_session(self.manager.session_factory).client('iam')
        value = self.data.get('value', True)
        res = []
        for r in resources:
            r = self._inline_policies(c, r)
            if len(r['c7n:InlinePolicies']) > 0 and value:
                res.append(r)
            if len(r['c7n:InlinePolicies']) == 0 and not value:
                res.append(r)
        return res


@User.filter_registry.register('policy')
class UserPolicy(ValueFilter):
    """Filter IAM users based on attached policy values

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-users-with-admin-access
            resource: iam-user
            filters:
              - type: policy
                key: PolicyName
                value: AdministratorAccess
    """

    schema = type_schema('policy', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('iam:ListAttachedUserPolicies',)

    def user_policies(self, user_set):
        client = local_session(self.manager.session_factory).client('iam')
        for u in user_set:
            if 'c7n:Policies' not in u:
                u['c7n:Policies'] = []
            aps = client.list_attached_user_policies(
                UserName=u['UserName'])['AttachedPolicies']
            for ap in aps:
                u['c7n:Policies'].append(
                    client.get_policy(PolicyArn=ap['PolicyArn'])['Policy'])

    def process(self, resources, event=None):
        user_set = chunks(resources, size=50)
        with self.executor_factory(max_workers=2) as w:
            self.log.debug(
                "Querying %d users policies" % len(resources))
            list(w.map(self.user_policies, user_set))

        matched = []
        for r in resources:
            for p in r['c7n:Policies']:
                if self.match(p) and r not in matched:
                    matched.append(r)
        return matched


@User.filter_registry.register('group')
class GroupMembership(ValueFilter):
    """Filter IAM users based on attached group values

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-users-in-admin-group
            resource: iam-user
            filters:
              - type: group
                key: GroupName
                value: Admins
    """

    schema = type_schema('group', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('iam:ListGroupsForUser',)

    def get_user_groups(self, client, user_set):
        for u in user_set:
            u['c7n:Groups'] = client.list_groups_for_user(
                UserName=u['UserName'])['Groups']

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('iam')
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for user_set in chunks(
                    [r for r in resources if 'c7n:Groups' not in r], size=50):
                futures.append(
                    w.submit(self.get_user_groups, client, user_set))
            for f in as_completed(futures):
                pass

        matched = []
        for r in resources:
            for p in r.get('c7n:Groups', []):
                if self.match(p) and r not in matched:
                    matched.append(r)
        return matched


@User.filter_registry.register('access-key')
class UserAccessKey(ValueFilter):
    """Filter IAM users based on access-key values

    By default multiple uses of this filter will match
    on any user key satisfying either filter. To find
    specific keys that match multiple access-key filters,
    use `match-operator: and`

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-users-with-active-keys
            resource: iam-user
            filters:
              - type: access-key
                key: Status
                value: Active
              - type: access-key
                match-operator: and
                key: CreateDate
                value_type: age
                value: 90
    """

    schema = type_schema(
        'access-key',
        rinherit=ValueFilter.schema,
        **{'match-operator': {'enum': ['and', 'or']}})
    schema_alias = False
    permissions = ('iam:ListAccessKeys',)
    annotation_key = 'c7n:AccessKeys'
    matched_annotation_key = 'c7n:matched-keys'
    annotate = False

    def get_user_keys(self, client, user_set):
        for u in user_set:
            u[self.annotation_key] = self.manager.retry(
                client.list_access_keys,
                UserName=u['UserName'])['AccessKeyMetadata']

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('iam')
        with self.executor_factory(max_workers=2) as w:
            augment_set = [r for r in resources if self.annotation_key not in r]
            self.log.debug(
                "Querying %d users' api keys" % len(augment_set))
            list(w.map(
                functools.partial(self.get_user_keys, client),
                chunks(augment_set, 50)))

        matched = []
        match_op = self.data.get('match-operator', 'or')
        for r in resources:
            keys = r[self.annotation_key]
            if self.matched_annotation_key in r and match_op == 'and':
                keys = r[self.matched_annotation_key]
            k_matched = []
            for k in keys:
                if self.match(k):
                    k_matched.append(k)
            for k in k_matched:
                k['c7n:match-type'] = 'access'
            self.merge_annotation(r, self.matched_annotation_key, k_matched)
            if k_matched:
                matched.append(r)
        return matched


# Mfa-device filter for iam-users
@User.filter_registry.register('mfa-device')
class UserMfaDevice(ValueFilter):
    """Filter iam-users based on mfa-device status

    :example:

    .. code-block:: yaml

        policies:
          - name: mfa-enabled-users
            resource: iam-user
            filters:
              - type: mfa-device
                key: UserName
                value: not-null
    """

    schema = type_schema('mfa-device', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('iam:ListMFADevices',)

    def __init__(self, *args, **kw):
        super(UserMfaDevice, self).__init__(*args, **kw)
        self.data['key'] = 'MFADevices'

    def process(self, resources, event=None):

        def _user_mfa_devices(resource):
            client = local_session(self.manager.session_factory).client('iam')
            resource['MFADevices'] = client.list_mfa_devices(
                UserName=resource['UserName'])['MFADevices']

        with self.executor_factory(max_workers=2) as w:
            query_resources = [
                r for r in resources if 'MFADevices' not in r]
            self.log.debug(
                "Querying %d users' mfa devices" % len(query_resources))
            list(w.map(_user_mfa_devices, query_resources))

        matched = []
        for r in resources:
            if self.match(r):
                matched.append(r)

        return matched


@User.action_registry.register('post-finding')
class UserFinding(OtherResourcePostFinding):

    def format_resource(self, r):
        if any(filter(lambda x: isinstance(x, UserAccessKey), self.manager.iter_filters())):
            details = {
                "UserName": "arn:aws:iam:{}:user/{}".format(
                    self.manager.config.account_id, r["c7n:AccessKeys"][0]["UserName"]
                ),
                "Status": r["c7n:AccessKeys"][0]["Status"],
                "CreatedAt": r["c7n:AccessKeys"][0]["CreateDate"].isoformat(),
            }
            accesskey = {
                "Type": "AwsIamAccessKey",
                "Id": r["c7n:AccessKeys"][0]["AccessKeyId"],
                "Region": self.manager.config.region,
                "Details": {"AwsIamAccessKey": filter_empty(details)},
            }
            return filter_empty(accesskey)
        else:
            return super(UserFinding, self).format_resource(r)


@User.action_registry.register('delete')
class UserDelete(BaseAction):
    """Delete a user or properties of a user.

    For example if you want to have a whitelist of valid (machine-)users
    and want to ensure that no users have been clicked without documentation.

    You can use both the 'credential' or the 'username'
    filter. 'credential' will have an SLA of 4h,
    (http://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_getting-report.html),
    but the added benefit of performing less API calls, whereas
    'username' will make more API calls, but have a SLA of your cache.

    :example:

      .. code-block:: yaml

        # using a 'credential' filter'
        - name: iam-only-whitelisted-users-credential
          resource: iam-user
          filters:
            - type: credential
              key: user
              op: not-in
              value:
                - valid-user-1
                - valid-user-2
          actions:
            - delete

        # using a 'username' filter with 'UserName'
        - name: iam-only-whitelisted-users-username
          resource: iam-user
          filters:
            - type: value
              key: UserName
              op: not-in
              value:
                - valid-user-1
                - valid-user-2
          actions:
            - delete

         # using a 'username' filter with 'Arn'
        - name: iam-only-whitelisted-users-arn
          resource: iam-user
          filters:
            - type: value
              key: Arn
              op: not-in
              value:
                - arn:aws:iam:123456789012:user/valid-user-1
                - arn:aws:iam:123456789012:user/valid-user-2
          actions:
            - delete

    Additionally, you can specify the options to delete properties of an iam-user,
    including console-access, access-keys, attached-user-policies,
    inline-user-policies, mfa-devices, groups,
    ssh-keys, signing-certificates, and service-specific-credentials.

    Note: using options will _not_ delete the user itself, only the items specified
    by ``options`` that are attached to the respective iam-user. To delete a user
    completely, use the ``delete`` action without specifying ``options``.

    :example:

        .. code-block:: yaml

            - name: delete-console-access-unless-valid
              comment: |
                finds iam-users with console access and deletes console access unless
                the username is included in whitelist
              resource: iam-user
              filters:
                - type: value
                  key: UserName
                  op: not-in
                  value:
                    - valid-user-1
                    - valid-user-2
                - type: credential
                  key: password_enabled
                  value: true
              actions:
                - type: delete
                  options:
                    - console-access

            - name: delete-misc-access-for-iam-user
              comment: |
                deletes multiple options from test_user
              resource: iam-user
              filters:
                - UserName: test_user
              actions:
                - type: delete
                  options:
                    - mfa-devices
                    - access-keys
                    - ssh-keys
    """

    ORDERED_OPTIONS = OrderedDict([
        ('console-access', 'delete_console_access'),
        ('access-keys', 'delete_access_keys'),
        ('attached-user-policies', 'delete_attached_user_policies'),
        ('inline-user-policies', 'delete_inline_user_policies'),
        ('mfa-devices', 'delete_hw_mfa_devices'),
        ('groups', 'delete_groups'),
        ('ssh-keys', 'delete_ssh_keys'),
        ('signing-certificates', 'delete_signing_certificates'),
        ('service-specific-credentials', 'delete_service_specific_credentials'),
    ])
    COMPOUND_OPTIONS = {
        'user-policies': ['attached-user-policies', 'inline-user-policies'],
    }

    schema = type_schema(
        'delete',
        options={
            'type': 'array',
            'items': {
                'type': 'string',
                'enum': list(ORDERED_OPTIONS.keys()) + list(COMPOUND_OPTIONS.keys()),
            }
        })

    permissions = (
        'iam:ListAttachedUserPolicies',
        'iam:ListAccessKeys',
        'iam:ListGroupsForUser',
        'iam:ListMFADevices',
        'iam:ListServiceSpecificCredentials',
        'iam:ListSigningCertificates',
        'iam:ListSSHPublicKeys',
        'iam:DeactivateMFADevice',
        'iam:DeleteAccessKey',
        'iam:DeleteLoginProfile',
        'iam:DeleteSigningCertificate',
        'iam:DeleteSSHPublicKey',
        'iam:DeleteUser',
        'iam:DeleteUserPolicy',
        'iam:DetachUserPolicy',
        'iam:RemoveUserFromGroup')

    @staticmethod
    def delete_console_access(client, r):
        try:
            client.delete_login_profile(
                UserName=r['UserName'])
        except ClientError as e:
            if e.response['Error']['Code'] not in ('NoSuchEntity',):
                raise

    @staticmethod
    def delete_access_keys(client, r):
        response = client.list_access_keys(UserName=r['UserName'])
        for access_key in response['AccessKeyMetadata']:
            client.delete_access_key(UserName=r['UserName'],
                                     AccessKeyId=access_key['AccessKeyId'])

    @staticmethod
    def delete_attached_user_policies(client, r):
        response = client.list_attached_user_policies(UserName=r['UserName'])
        for user_policy in response['AttachedPolicies']:
            client.detach_user_policy(
                UserName=r['UserName'], PolicyArn=user_policy['PolicyArn'])

    @staticmethod
    def delete_inline_user_policies(client, r):
        response = client.list_user_policies(UserName=r['UserName'])
        for user_policy_name in response['PolicyNames']:
            client.delete_user_policy(
                UserName=r['UserName'], PolicyName=user_policy_name)

    @staticmethod
    def delete_hw_mfa_devices(client, r):
        response = client.list_mfa_devices(UserName=r['UserName'])
        for mfa_device in response['MFADevices']:
            client.deactivate_mfa_device(
                UserName=r['UserName'], SerialNumber=mfa_device['SerialNumber'])

    @staticmethod
    def delete_groups(client, r):
        response = client.list_groups_for_user(UserName=r['UserName'])
        for user_group in response['Groups']:
            client.remove_user_from_group(
                UserName=r['UserName'], GroupName=user_group['GroupName'])

    @staticmethod
    def delete_ssh_keys(client, r):
        response = client.list_ssh_public_keys(UserName=r['UserName'])
        for key in response.get('SSHPublicKeys', ()):
            client.delete_ssh_public_key(
                UserName=r['UserName'], SSHPublicKeyId=key['SSHPublicKeyId'])

    @staticmethod
    def delete_signing_certificates(client, r):
        response = client.list_signing_certificates(UserName=r['UserName'])
        for cert in response.get('Certificates', ()):
            client.delete_signing_certificate(
                UserName=r['UserName'], CertificateId=cert['CertificateId'])

    @staticmethod
    def delete_service_specific_credentials(client, r):
        # Service specific user credentials (codecommit)
        response = client.list_service_specific_credentials(UserName=r['UserName'])
        for screds in response.get('ServiceSpecificCredentials', ()):
            client.delete_service_specific_credential(
                UserName=r['UserName'],
                ServiceSpecificCredentialId=screds['ServiceSpecificCredentialId'])

    @staticmethod
    def delete_user(client, r):
        client.delete_user(UserName=r['UserName'])

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iam')
        self.log.debug('Deleting user %s options: %s' %
            (len(resources), self.data.get('options', 'all')))
        for r in resources:
            self.process_user(client, r)

    def process_user(self, client, r):
        user_options = self.data.get('options', list(self.ORDERED_OPTIONS.keys()))
        # resolve compound options
        for cmd in self.COMPOUND_OPTIONS:
            if cmd in user_options:
                user_options += self.COMPOUND_OPTIONS[cmd]
        # process options in ordered fashion
        for cmd in self.ORDERED_OPTIONS:
            if cmd in user_options:
                op = getattr(self, self.ORDERED_OPTIONS[cmd])
                op(client, r)
        if not self.data.get('options'):
            self.delete_user(client, r)


@User.action_registry.register('remove-keys')
class UserRemoveAccessKey(BaseAction):
    """Delete or disable user's access keys.

    For example if we wanted to disable keys after 90 days of non-use and
    delete them after 180 days of nonuse:

    :example:

        .. code-block:: yaml

         - name: iam-mfa-active-key-no-login
           resource: iam-user
           actions:
             - type: remove-keys
               disable: true
               age: 90
             - type: remove-keys
               age: 180
    """

    schema = type_schema(
        'remove-keys',
        matched={'type': 'boolean'},
        age={'type': 'number'},
        disable={'type': 'boolean'})
    permissions = ('iam:ListAccessKeys', 'iam:UpdateAccessKey',
                   'iam:DeleteAccessKey')

    def validate(self):
        if self.data.get('matched') and self.data.get('age'):
            raise PolicyValidationError(
                "policy:%s cant mix matched and age parameters")
        ftypes = {f.type for f in self.manager.iter_filters()}
        if 'credential' in ftypes and 'access-key' in ftypes:
            raise PolicyValidationError(
                "policy:%s cant mix credential and access-key filters w/ delete action")
        return self

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iam')

        age = self.data.get('age')
        disable = self.data.get('disable')
        matched = self.data.get('matched')

        if age:
            threshold_date = datetime.datetime.now(tz=tzutc()) - timedelta(age)

        for r in resources:
            if 'c7n:AccessKeys' not in r:
                r['c7n:AccessKeys'] = client.list_access_keys(
                    UserName=r['UserName'])['AccessKeyMetadata']

            keys = r['c7n:AccessKeys']
            if matched:
                m_keys = resolve_credential_keys(
                    r.get(CredentialReport.matched_annotation_key),
                    keys)
                assert m_keys, "shouldn't have gotten this far without keys"
                keys = m_keys

            for k in keys:
                if age:
                    if not k['CreateDate'] < threshold_date:
                        continue
                if disable:
                    client.update_access_key(
                        UserName=r['UserName'],
                        AccessKeyId=k['AccessKeyId'],
                        Status='Inactive')
                else:
                    client.delete_access_key(
                        UserName=r['UserName'],
                        AccessKeyId=k['AccessKeyId'])


def resolve_credential_keys(m_keys, keys):
    res = []
    for k in m_keys:
        if k['c7n:match-type'] == 'credential':
            c_date = parse_date(k['last_rotated'])
            for ak in keys:
                if c_date == ak['CreateDate']:
                    ak = dict(ak)
                    ak['c7n:match-type'] = 'access'
                    if ak not in res:
                        res.append(ak)
        elif k not in res:
            res.append(k)
    return res


#################
#   IAM Groups  #
#################


@Group.filter_registry.register('has-users')
class IamGroupUsers(Filter):
    """Filter IAM groups that have users attached based on True/False value:
    True: Filter all IAM groups with users assigned to it
    False: Filter all IAM groups without any users assigned to it

    :example:

    .. code-block:: yaml

      - name: empty-iam-group
        resource: iam-group
        filters:
          - type: has-users
            value: False
    """
    schema = type_schema('has-users', value={'type': 'boolean'})
    permissions = ('iam:GetGroup',)

    def _user_count(self, client, resource):
        return len(client.get_group(GroupName=resource['GroupName'])['Users'])

    def process(self, resources, events=None):
        c = local_session(self.manager.session_factory).client('iam')
        if self.data.get('value', True):
            return [r for r in resources if self._user_count(c, r) > 0]
        return [r for r in resources if self._user_count(c, r) == 0]


@Group.filter_registry.register('has-inline-policy')
class IamGroupInlinePolicy(Filter):
    """Filter IAM groups that have an inline-policy based on boolean value:
    True: Filter all groups that have an inline-policy attached
    False: Filter all groups that do not have an inline-policy attached

    :example:

    .. code-block:: yaml

      - name: iam-groups-with-inline-policy
        resource: iam-group
        filters:
          - type: has-inline-policy
            value: True
    """
    schema = type_schema('has-inline-policy', value={'type': 'boolean'})
    permissions = ('iam:ListGroupPolicies',)

    def _inline_policies(self, client, resource):
        resource['c7n:InlinePolicies'] = client.list_group_policies(
            GroupName=resource['GroupName'])['PolicyNames']
        return resource

    def process(self, resources, events=None):
        c = local_session(self.manager.session_factory).client('iam')
        value = self.data.get('value', True)
        res = []
        for r in resources:
            r = self._inline_policies(c, r)
            if len(r['c7n:InlinePolicies']) > 0 and value:
                res.append(r)
            if len(r['c7n:InlinePolicies']) == 0 and not value:
                res.append(r)
        return res


@Group.action_registry.register('delete')
class UserGroupDelete(BaseAction):
    """Delete an IAM User Group.

    For example, if you want to delete a group named 'test'.

    :example:

      .. code-block:: yaml

        - name: iam-delete-user-group
          resource: aws.iam-group
          filters:
            - type: value
              key: GroupName
              value: test
          actions:
            - type: delete
              force: True
    """
    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = ('iam:DeleteGroup', 'iam:RemoveUserFromGroup')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iam')
        for r in resources:
            self.process_group(client, r)

    def process_group(self, client, r):
        error = None
        force = self.data.get('force', False)
        if force:
            users = client.get_group(GroupName=r['GroupName']).get('Users', [])
            for user in users:
                client.remove_user_from_group(
                    UserName=user['UserName'], GroupName=r['GroupName'])

        try:
            client.delete_group(GroupName=r['GroupName'])
        except client.exceptions.DeleteConflictException as e:
            self.log.warning(
                ("Group:%s cannot be deleted, "
                 "set force to remove all users from group")
                % r['Arn'])
            error = e
        except (client.exceptions.NoSuchEntityException,
                client.exceptions.UnmodifiableEntityException):
            pass
        if error:
            raise error


class SamlProviderDescribe(DescribeSource):

    def augment(self, resources):
        super().augment(resources)
        for r in resources:
            md = r.get('SAMLMetadataDocument')
            if not md:
                continue
            root = sso_metadata(md)
            r['IDPSSODescriptor'] = root['IDPSSODescriptor']
        return resources

    def get_permissions(self):
        return ('iam:GetSAMLProvider', 'iam:ListSAMLProviders')


def sso_metadata(md):
    root = ElementTree.fromstringlist(md)
    d = {}
    _sso_recurse(root, d)
    return d


def _sso_recurse(node, d):
    d.update(node.attrib)
    for c in node:
        k = c.tag.split('}', 1)[-1]
        cd = {}
        if k in d:
            if not isinstance(d[k], list):
                d[k] = [d[k]]
            d[k].append(cd)
        else:
            d[k] = cd
        _sso_recurse(c, cd)
    if node.text and node.text.strip():
        d['Value'] = node.text.strip()


@resources.register('iam-saml-provider')
class SamlProvider(QueryResourceManager):
    """SAML SSO Provider

    we parse and expose attributes of the SAML Metadata XML Document
    as resources attribute for use with custodian's standard value filter.
    """

    class resource_type(TypeInfo):

        service = 'iam'
        name = id = 'Arn'
        enum_spec = ('list_saml_providers', 'SAMLProviderList', None)
        detail_spec = ('get_saml_provider', 'SAMLProviderArn', 'Arn', None)
        arn = 'Arn'
        arn_type = 'saml-provider'
        global_resource = True

    source_mapping = {'describe': SamlProviderDescribe}


class OpenIdDescribe(DescribeSource):

    def get_permissions(self):
        return ('iam:GetOpenIDConnectProvider', 'iam:ListOpenIDConnectProviders')


@resources.register('iam-oidc-provider')
class OpenIdProvider(QueryResourceManager):

    class resource_type(TypeInfo):

        service = 'iam'
        name = id = 'Arn'
        enum_spec = ('list_open_id_connect_providers', 'OpenIDConnectProviderList', None)
        detail_spec = ('get_open_id_connect_provider', 'OpenIDConnectProviderArn', 'Arn', None)
        arn = 'Arn'
        arn_type = 'oidc-provider'
        global_resource = True

    source_mapping = {'describe': OpenIdDescribe}
