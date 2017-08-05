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
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('identity-pool')
class CognitoIdentityPool(QueryResourceManager):

    class resource_type(object):
        service = 'cognito-identity'
        enum_spec = ('list_identity_pools', 'IdentityPools', None)
        detail_spec = (
            'describe_identity_pool', 'IdentityPoolId', 'IdentityPoolId')
        id = 'IdentityPoolId'
        name = 'IdentityPoolName'
        filter_name = None
        dimension = None


@resources.register('user-pool')
class CognitoUserPool(QueryResourceManager):

    class resource_type(object):
        service = "cognito-idp"
        enum_spec = ('list_user_pools', 'UserPools', None)
        detail_spec = (
            'describe_user_pool', 'UserPoolId', 'Id', 'UserPool')
        id = 'Id'
        name = 'Name'
        filter_name = None
        dimension = None
