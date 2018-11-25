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

from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema


@resources.register('identity-pool')
class CognitoIdentityPool(QueryResourceManager):

    class resource_type(object):
        service = 'cognito-identity'
        enum_spec = ('list_identity_pools', 'IdentityPools', {'MaxResults': 60})
        detail_spec = (
            'describe_identity_pool', 'IdentityPoolId', 'IdentityPoolId', None)
        id = 'IdentityPoolId'
        name = 'IdentityPoolName'
        filter_name = None
        dimension = None


@CognitoIdentityPool.action_registry.register('delete')
class DeleteIdentityPool(BaseAction):
    """Action to delete cognito identity pool

    It is recommended to use a filter to avoid unwanted deletion of pools

    :example:

    .. code-block:: yaml

            policies:
              - name: identity-pool-delete
                resource: identity-pool
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("cognito-identity:DeleteIdentityPool",)

    def process(self, pools):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_pool, pools))

    def process_pool(self, pool):
        client = local_session(
            self.manager.session_factory).client('cognito-identity')
        try:
            client.delete_identity_pool(IdentityPoolId=pool['IdentityPoolId'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting identity pool:\n %s" % e)


@resources.register('user-pool')
class CognitoUserPool(QueryResourceManager):

    class resource_type(object):
        service = "cognito-idp"
        enum_spec = ('list_user_pools', 'UserPools', {'MaxResults': 60})
        detail_spec = (
            'describe_user_pool', 'UserPoolId', 'Id', 'UserPool')
        id = 'Id'
        name = 'Name'
        filter_name = None
        dimension = None


@CognitoUserPool.action_registry.register('delete')
class DeleteUserPool(BaseAction):
    """Action to delete cognito user pool

    It is recommended to use a filter to avoid unwanted deletion of pools

    :example:

    .. code-block:: yaml

            policies:
              - name: user-pool-delete
                resource: user-pool
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("cognito-idp:DeleteUserPool",)

    def process(self, pools):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_pool, pools))

    def process_pool(self, pool):
        client = local_session(
            self.manager.session_factory).client('cognito-idp')
        try:
            client.delete_user_pool(UserPoolId=pool['Id'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting user pool:\n %s" % e)
