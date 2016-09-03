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
from c7n.filters import ValueFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema


@resources.register('iam-group')
class Group(QueryResourceManager):

    resource_type = 'aws.iam.group'


@resources.register('iam-role')
class Role(QueryResourceManager):

    resource_type = 'aws.iam.role'


@resources.register('iam-user')
class User(QueryResourceManager):

    resource_type = 'aws.iam.user'


@User.filter_registry.register('policy')
class UserAttachedPolicy(ValueFilter):

    schema = type_schema('policy', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):

        def _user_policies(resource):
            client = local_session(self.manager.session_factory).client('iam')
            resource['AttachedPolicies'] = client.list_attached_user_policies(
                UserName=resource['UserName'])['AttachedPolicies']

        with self.executor_factory(max_workers=2) as w:
            query_resources = [
                r for r in resources if 'AttachedPolicies' not in r]
            self.log.debug("Querying %d users policies" % len(query_resources))
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
            self.log.debug("Querying %d users' api keys" % len(query_resources))
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
            self.log.debug("Querying %d users' mfa devices" % len(query_resources))
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
            threshold_date = datetime(tz=tzutc()) - timedelta(age)

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


@resources.register('iam-policy')
class Policy(QueryResourceManager):

    resource_type = 'aws.iam.policy'


@resources.register('iam-profile')
class InstanceProfile(QueryResourceManager):

    resource_type = 'aws.iam.instance-profile'


@resources.register('iam-certificate')
class ServerCerficate(QueryResourceManager):

    resource_type = 'aws.iam.server-certificate'
