# Copyright 2016 Capital One Services, LLC
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

from datetime import datetime, timedelta
from dateutil.parser import parse
from dateutil.tz import tzutc

from c7n.actions import BaseAction
from c7n.filters import ValueFilter, Filter
from c7n.manager import resources
from c7n.query import QueryResourceManager, ResourceQuery
from c7n.utils import local_session, type_schema


@resources.register('iam-group')
class Group(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.iam.group')):
        config_type = "AWS::IAM::Group"


@resources.register('iam-role')
class Role(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.iam.role')):
        config_type = "AWS::IAM::Role"


@resources.register('iam-user')
class User(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.iam.user')):
        config_type = "AWS::IAM::User"


@resources.register('iam-policy')
class Policy(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.iam.policy')):
        config_type = "AWS::IAM::Policy"



@resources.register('iam-profile')
class InstanceProfile(QueryResourceManager):
    resource_type = 'aws.iam.instance-profile'


@resources.register('iam-certificate')
class ServerCertificate(QueryResourceManager):
    resource_type = 'aws.iam.server-certificate'


class IamRoleUsage(Filter):

    def service_role_usage(self):
        results = set()
        results.update(self.scan_lambda_roles())
        results.update(self.scan_ecs_roles())
        results.update(self.scan_asg_roles())
        results.update(self.scan_ec2_roles())
        return results

    def instance_profile_usage(self):
        results = set()
        results.update(self.scan_asg_roles())
        results.update(self.scan_ec2_roles())
        return results

    def scan_lambda_roles(self):
        from c7n.resources.awslambda import AWSLambda
        manager = AWSLambda(self.manager.ctx, {})
        return [r['Role'] for r in manager.resources() if 'Role' in r]

    def scan_ecs_roles(self):
        results = []
        client = local_session(self.manager.session_factory).client('ecs')
        for cluster in client.describe_clusters()['clusters']:
            svcs = client.list_services(cluster=cluster)['serviceArns']
            for svc in client.describe_services(
                    cluster=cluster, services=svcs)['services']:
                if 'roleArn' not in svc:
                    continue
                results.append(svc['roleArn'])
        return results

    def scan_asg_roles(self):
        from c7n.resources.asg import LaunchConfig
        manager = LaunchConfig(self.manager.ctx, {
            'resource': 'launch-config'})
        return [r['IamInstanceProfile'] for r in manager.resources()
                if 'IamInstanceProfile' in r]

    def scan_ec2_roles(self):
        from c7n.resources.ec2 import EC2
        manager = EC2(self.manager.ctx, {})

        results = []
        for e in manager.resources():
            if 'Instances' not in e:
                continue
            for i in e['Instances']:
                if 'IamInstanceProfile' not in i:
                    continue
                results.append(i['IamInstanceProfile']['Arn'])
        return results


###################
#    IAM Roles    #
###################


@Role.filter_registry.register('used')
class UsedIamRole(IamRoleUsage):

    schema = type_schema('used')

    def process(self, resources, event=None):
        roles = self.service_role_usage()
        results = []
        for r in resources:
            if r['Arn'] in roles or r['RoleName'] in roles:
                results.append(r)
        self.log.info("%d of %d iam roles currently used." % (
            len(results), len(resources)))
        return results


@Role.filter_registry.register('unused')
class UnusedIamRole(IamRoleUsage):

    schema = type_schema('unused')

    def process(self, resources, event=None):
        roles = self.service_role_usage()
        results = []
        for r in resources:
            if r['Arn'] not in roles or r['RoleName'] not in roles:
                results.append(r)
        self.log.info("%d of %d iam roles not currently used." % (
            len(results), len(resources)))
        return results


@Role.filter_registry.register('has-inline-policy')
class IamRoleInlinePolicy(Filter):
    """
        Filter IAM roles that have an inline-policy attached

        True: Filter roles that have an inline-policy
        False: Filter roles that do not have an inline-policy
    """
    schema = type_schema('has-inline-policy', value={'type': 'boolean'})

    def _inline_policies(self, client, resource):
        return len(client.list_role_policies(
            RoleName=resource['RoleName'])['PolicyNames'])

    def process(self, resources, event=None):
        c = local_session(self.manager.session_factory).client('iam')
        if self.data.get('value', True):
            return [r for r in resources if self._inline_policies(c, r) > 0]
        return [r for r in resources if self._inline_policies(c, r) == 0]


######################
#    IAM Policies    #
######################


@Policy.filter_registry.register('used')
class UsedIamPolicies(Filter):

    schema = type_schema('used')

    def process(self, resources, event=None):
        return [r for r in resources if r['AttachmentCount'] > 0]


@Policy.filter_registry.register('unused')
class UnusedIamPolicies(Filter):

    schema = type_schema('unused')

    def process(self, resources, event=None):
        return [r for r in resources if r['AttachmentCount'] == 0]


###############################
#    IAM Instance Profiles    #
###############################


@InstanceProfile.filter_registry.register('used')
class UsedInstanceProfiles(IamRoleUsage):

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

    schema = type_schema('unused')

    def process(self, resources, event=None):
        results = []
        profiles = self.instance_profile_usage()
        for r in resources:
            if (r['Arn'] not in profiles or
                        r['InstanceProfileName'] not in profiles):
                results.append(r)
        self.log.info(
            "%d of %d instance profiles currently not in use." % (
                len(results), len(resources)))
        return results


@InstanceProfile.filter_registry.register('attached')
class AttachedInstanceProfiles(Filter):

    schema = type_schema('attached')

    def process(self, resources, event=None):
        results = []
        for r in resources:
            if len(r['Roles']) != 0:
                results.append(r)
        self.log.info(
            "%d of %d instance profiles attached to a role." % (
                len(results), len(resources)))
        return results


@InstanceProfile.filter_registry.register('unattached')
class UnattachedInstanceProfiles(Filter):

    schema = type_schema('unattached')

    def process(self, resources, event=None):
        results = []
        for r in resources:
            if len(r['Roles']) == 0:
                results.append(r)
        self.log.info(
            "%d of %d instance profiles not attached to a role." % (
                len(results), len(resources)))
        return results


###################
#    IAM Users    #
###################


@User.filter_registry.register('policy')
class UserAttachedPolicy(Filter):

    schema = type_schema('policy')

    def process(self, resources, event=None):

        def _user_policies(resource):
            client = local_session(self.manager.session_factory).client('iam')
            resource['AttachedPolicies'] = client.list_attached_user_policies(
                UserName=resource['UserName'])['AttachedPolicies']

        with self.executor_factory(max_workers=2) as w:
            query_resources = [
                r for r in resources if 'AttachedPolicies' not in r]
            self.log.debug(
                "Querying %d users policies" % len(query_resources))
            list(w.map(_user_policies, query_resources))

        matched = []
        for r in resources:
            for p in r['AttachedPolicies']:
                if self.match(p):
                    matched.append(r)
                    break
        return matched


@User.filter_registry.register('access-key')
class UserAccessKey(ValueFilter):

    schema = type_schema('access-key', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):

        def _user_keys(resource):
            client = local_session(self.manager.session_factory).client('iam')
            resource['AccessKeys'] = client.list_access_keys(
                UserName=resource['UserName'])['AccessKeyMetadata']

        with self.executor_factory(max_workers=2) as w:
            query_resources = [
                r for r in resources if 'AccessKeys' not in r]
            self.log.debug(
                "Querying %d users' api keys" % len(query_resources))
            list(w.map(_user_keys, query_resources))

        matched = []
        for r in resources:
            for p in r['AccessKeys']:
                if self.match(p):
                    matched.append(r)
                    break
        return matched


# Mfa-device filter for iam-users
@User.filter_registry.register('mfa-device')
class UserMfaDevice(ValueFilter):

    schema = type_schema('mfa-device', rinherit=ValueFilter.schema)

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


@User.action_registry.register('remove-keys')
class UserRemoveAccessKey(BaseAction):

    schema = type_schema(
        'remove-keys', age={'type': 'number'}, disable={'type': 'boolean'})

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('iam')

        age = self.data.get('age')
        disable = self.data.get('disable')

        if age:
            threshold_date = datetime().now(tz=tzutc()) - timedelta(age)

        for r in resources:
            if 'AccessKeys' not in r:
                r['AccessKeys'] = client.list_access_keys(
                    UserName=r['UserName'])['AccessKeyMetadata']
            keys = r['AccessKeys']
            for k in keys:
                if age:
                    if not parse(k['CreateDate']) < threshold_date:
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
    """
        Filter IAM groups that have users attached based on True/False value:

        True: Filter all IAM groups with users assigned to it
        False: Filter all IAM groups without any users assigned to it
    """
    schema = type_schema('has-users', value={'type': 'boolean'})

    def _user_count(self, client, resource):
        return len(client.get_group(GroupName=resource['GroupName'])['Users'])

    def process(self, resources, events=None):
        c = local_session(self.manager.session_factory).client('iam')
        value = self.data.get('value')
        if self.data.get('value', True):
            return [r for r in resources if self._user_count(c, r) > 0]
        return [r for r in resources if self._user_count(c, r) == 0]


@Group.filter_registry.register('has-inline-policy')
class IamGroupInlinePolicy(Filter):
    """
        Filter IAM groups that have an inline-policy based on boolean value:

        True: Filter all groups that have an inline-policy attached
        False: Filter all groups that do not have an inline-policy attached
    """
    schema = type_schema('has-inline-policy', value={'type': 'boolean'})

    def _inline_policies(self, client, resource):
        return len(client.list_group_policies(
            GroupName=resource['GroupName'])['PolicyNames'])

    def process(self, resources, events=None):
        c = local_session(self.manager.session_factory).client('iam')
        if self.data.get('value', True):
            return [r for r in resources if self._inline_policies(c, r) > 0]
        return [r for r in resources if self._inline_policies(c, r) == 0]
