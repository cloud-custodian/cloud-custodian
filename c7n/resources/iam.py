# Copyright 2016-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

import csv
import datetime
import io
from datetime import timedelta
import itertools
import time

from concurrent.futures import as_completed
from dateutil.tz import tzutc
import six
from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.filters import ValueFilter, Filter, OPERATORS
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, DescribeSource
from c7n.resolver import ValuesFrom
from c7n.utils import local_session, type_schema, chunks


@resources.register('iam-group')
class Group(QueryResourceManager):

    class resource_type(object):
        service = 'iam'
        type = 'group'
        enum_spec = ('list_groups', 'Groups', None)
        detail_spec = None
        id = 'GroupId'
        name = 'GroupName'
        filter_name = None
        date = 'CreateDate'
        dimension = None
        config_type = "AWS::IAM::Group"


@resources.register('iam-role')
class Role(QueryResourceManager):

    class resource_type(object):
        service = 'iam'
        type = 'role'
        enum_spec = ('list_roles', 'Roles', None)
        detail_spec = None
        id = 'RoleId'
        filter_name = None
        name = 'RoleName'
        date = 'CreateDate'
        dimension = None
        config_type = "AWS::IAM::Role"


@resources.register('iam-user')
class User(QueryResourceManager):

    class resource_type(object):
        service = 'iam'
        type = 'user'
        enum_spec = ('list_users', 'Users', None)
        filter_name = None
        id = name = 'UserName'
        date = 'CreateDate'
        dimension = None
        config_type = "AWS::IAM::User"

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeUser(self)
        return super(User, self).get_source(source_type)


class DescribeUser(DescribeSource):

    def get_resources(self, resource_ids, cache=True):
        client = local_session(self.manager.session_factory).client('iam')
        resources = []
        for rid in resource_ids:
            try:
                resources.append(client.get_user(UserName=rid).get('User'))
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchEntityException':
                    continue
                raise
        return resources


@resources.register('iam-policy')
class Policy(QueryResourceManager):

    class resource_type(object):
        service = 'iam'
        type = 'policy'
        enum_spec = ('list_policies', 'Policies', None)
        id = 'PolicyId'
        name = 'PolicyName'
        date = 'CreateDate'
        dimension = None
        config_type = "AWS::IAM::Policy"
        filter_name = None

    arn_path_prefix = "aws:policy/"

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribePolicy(self)
        return super(Policy, self).get_source(source_type)


class DescribePolicy(DescribeSource):

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


@resources.register('iam-profile')
class InstanceProfile(QueryResourceManager):

    class resource_type(object):
        service = 'iam'
        type = 'instance-profile'
        enum_spec = ('list_instance_profiles', 'InstanceProfiles', None)
        id = 'InstanceProfileId'
        filter_name = None
        name = 'InstanceProfileId'
        date = 'CreateDate'
        dimension = None


@resources.register('iam-certificate')
class ServerCertificate(QueryResourceManager):

    class resource_type(object):
        service = 'iam'
        type = 'server-certificate'
        enum_spec = ('list_server_certificates',
                     'ServerCertificateMetadataList',
                     None)
        id = 'ServerCertificateId'
        filter_name = None
        name = 'ServerCertificateName'
        date = 'Expiration'
        dimension = None


class IamRoleUsage(Filter):

    def get_permissions(self):
        perms = list(itertools.chain([
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
        return len(client.list_role_policies(
            RoleName=resource['RoleName'])['PolicyNames'])

    def process(self, resources, event=None):
        c = local_session(self.manager.session_factory).client('iam')
        if self.data.get('value', True):
            return [r for r in resources if self._inline_policies(c, r) > 0]
        return [r for r in resources if self._inline_policies(c, r) == 0]


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


######################
#    IAM Policies    #
######################


@Policy.filter_registry.register('used')
class UsedIamPolicies(Filter):
    """Filter IAM policies that are being used

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
        return [r for r in resources if r['AttachmentCount'] > 0]


@Policy.filter_registry.register('unused')
class UnusedIamPolicies(Filter):
    """Filter IAM policies that are not being used

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
        return [r for r in resources if r['AttachmentCount'] == 0]


@Policy.filter_registry.register('has-allow-all')
class AllowAllIamPolicies(Filter):
    """Check if IAM policy resource(s) have allow-all IAM policy statement block.

    This allows users to implement CIS AWS check 1.24 which states that no
    policy must exist with the following requirements.

    Policy must have 'Action' and Resource = '*' with 'Effect' = 'Allow'

    The policy will trigger on the following IAM policy (statement).
    For example:

    .. code-block: json
     {
         'Version': '2012-10-17',
         'Statement': [{
             'Action': '*',
             'Resource': '*',
             'Effect': 'Allow'
         }]
     }

    Additionally, the policy checks if the statement has no 'Condition' or
    'NotAction'

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
                    isinstance(s['Action'], six.string_types) and
                    s['Action'] == "*" and
                    'Resource' in s and
                    isinstance(s['Resource'], six.string_types) and
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

###############################
#    IAM Instance Profiles    #
###############################


@InstanceProfile.filter_registry.register('used')
class UsedInstanceProfiles(IamRoleUsage):
    """Filter IAM profiles that are being used

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

    The IAM Credential report ( https://goo.gl/sbEPtM ) aggregates
    multiple pieces of information on iam users. This makes it highly
    efficient for querying multiple aspects of a user that would
    otherwise require per user api calls.

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
           key: access_keys.last_used
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
        value_type=ValueFilter.schema['properties']['value_type'],

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
        value={'oneOf': [
            {'type': 'array'},
            {'type': 'string'},
            {'type': 'boolean'},
            {'type': 'number'},
            {'type': 'null'}]},
        op={'enum': list(OPERATORS.keys())},
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
        if isinstance(data, six.binary_type):
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
            if obj.get('active', False):
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

    def match(self, info):
        if info is None:
            return False
        k = self.data.get('key')
        if '.' not in k:
            vf = ValueFilter(self.data)
            vf.annotate = False
            return vf(info)

        prefix, sk = k.split('.', 1)
        vf = ValueFilter(self.matcher_config)
        vf.annotate = False
        for v in info.get(prefix, ()):
            if vf.match(v):
                return True


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
            if self.match(info):
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

    def _num_inline_policies(self, client, resource):
        return len(client.list_user_policies(
            UserName=resource['UserName'])['PolicyNames'])

    def process(self, resources, event=None):
        c = local_session(self.manager.session_factory).client('iam')
        if self.data.get('value', True):
            return [r for r in resources if self._num_inline_policies(c, r) > 0]
        return [r for r in resources if self._num_inline_policies(c, r) == 0]


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
            for p in r['c7n:Groups']:
                if self.match(p) and r not in matched:
                    matched.append(r)
        return matched


@User.filter_registry.register('access-key')
class UserAccessKey(ValueFilter):
    """Filter IAM users based on access-key values

    :example:

    .. code-block:: yaml

        policies:
          - name: iam-users-with-active-keys
            resource: iam-user
            filters:
              - type: access-key
                key: Status
                value: Active
    """

    schema = type_schema('access-key', rinherit=ValueFilter.schema)
    permissions = ('iam:ListAccessKeys',)

    def user_keys(self, user_set):
        client = local_session(self.manager.session_factory).client('iam')
        for u in user_set:
            u['c7n:AccessKeys'] = client.list_access_keys(
                UserName=u['UserName'])['AccessKeyMetadata']

    def process(self, resources, event=None):
        user_set = chunks(resources, size=50)
        with self.executor_factory(max_workers=2) as w:
            self.log.debug(
                "Querying %d users' api keys" % len(resources))
            list(w.map(self.user_keys, user_set))

        matched = []
        for r in resources:
            for k in r['c7n:AccessKeys']:
                if self.match(k):
                    matched.append(r)
                    break
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
    permissions = ('iam:ListMfaDevices',)

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


@User.action_registry.register('delete')
class UserDelete(BaseAction):
    """Delete a user.

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
        - name: iam-only-whitelisted-users
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
        - name: iam-only-whitelisted-users
          resource: iam-user
          filters:
            - type: username
              key: UserName
              op: not-in
              value:
                - valid-user-1
                - valid-user-2
          actions:
            - delete

         # using a 'username' filter with 'Arn'
        - name: iam-only-whitelisted-users
          resource: iam-user
          filters:
            - type: username
              key: Arn
              op: not-in
              value:
                - arn:aws:iam:123456789012:user/valid-user-1
                - arn:aws:iam:123456789012:user/valid-user-2
          actions:
            - delete

    """
    schema = type_schema('delete')
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
        'iam:DetachUserPolicy',
        'iam:RemoveUserFromGroup')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iam')
        for r in resources:
            self.log.debug('Deleting user %s' % r['UserName'])
            self.process_user(client, r)

    def process_user(self, client, r):
        try:
            client.delete_login_profile(
                UserName=r['UserName'])
        except ClientError as e:
            if e.response['Error']['Code'] not in ('NoSuchEntity',):
                raise

        # Access Keys
        response = client.list_access_keys(UserName=r['UserName'])
        for access_key in response['AccessKeyMetadata']:
            client.delete_access_key(UserName=r['UserName'],
                                     AccessKeyId=access_key['AccessKeyId'])

        # User Policies
        response = client.list_attached_user_policies(UserName=r['UserName'])
        for user_policy in response['AttachedPolicies']:
            client.detach_user_policy(
                UserName=r['UserName'], PolicyArn=user_policy['PolicyArn'])

        # HW MFA Devices
        response = client.list_mfa_devices(UserName=r['UserName'])
        for mfa_device in response['MFADevices']:
            client.deactivate_mfa_device(
                UserName=r['UserName'], SerialNumber=mfa_device['SerialNumber'])

        # Groups
        response = client.list_groups_for_user(UserName=r['UserName'])
        for user_group in response['Groups']:
            client.remove_user_from_group(
                UserName=r['UserName'], GroupName=user_group['GroupName'])

        # SSH Keys
        response = client.list_ssh_public_keys(UserName=r['UserName'])
        for key in response.get('SSHPublicKeys', ()):
            client.delete_ssh_public_key(
                UserName=r['UserName'], SSHPublicKeyId=key['SSHPublicKeyId'])

        # Signing Certificates
        response = client.list_signing_certificates(UserName=r['UserName'])
        for cert in response.get('Certificates', ()):
            client.delete_signing_certificate(
                UserName=r['UserName'], CertificateId=cert['CertificateId'])

        # Service specific user credentials (codecommit)
        response = client.list_service_specific_credentials(UserName=r['UserName'])
        for screds in response.get('ServiceSpecificCredentials', ()):
            client.delete_service_specific_credential(
                UserName=r['UserName'],
                ServiceSpecificCredentialId=screds['ServiceSpecificCredentialId'])

        client.delete_user(UserName=r['UserName'])


@User.action_registry.register('remove-keys')
class UserRemoveAccessKey(BaseAction):
    """Delete or disable user's access keys.

    For example if we wanted to disable keys after 90 days of non-use and
    delete them after 180 days of nonuse:

    :example:

        .. code-block:: yaml

         - name: iam-mfa-active-keys-no-login
           resource: iam-user
           actions:
             - type: remove-keys
               disable: true
               age: 90
             - type: remove-keys
               age: 180
    """

    schema = type_schema(
        'remove-keys', age={'type': 'number'}, disable={'type': 'boolean'})
    permissions = ('iam:ListAccessKeys', 'iam:UpdateAccessKey',
                   'iam:DeleteAccessKey')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iam')

        age = self.data.get('age')
        disable = self.data.get('disable')

        if age:
            threshold_date = datetime.datetime.now(tz=tzutc()) - timedelta(age)

        for r in resources:
            if 'c7n:AccessKeys' not in r:
                r['c7n:AccessKeys'] = client.list_access_keys(
                    UserName=r['UserName'])['AccessKeyMetadata']
            keys = r['c7n:AccessKeys']
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
        return len(client.list_group_policies(
            GroupName=resource['GroupName'])['PolicyNames'])

    def process(self, resources, events=None):
        c = local_session(self.manager.session_factory).client('iam')
        if self.data.get('value', True):
            return [r for r in resources if self._inline_policies(c, r) > 0]
        return [r for r in resources if self._inline_policies(c, r) == 0]
