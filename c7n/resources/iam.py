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


from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('iam-group')
class Group(QueryResourceManager):

    resource_type = 'aws.iam.group'


@resources.register('iam-role')
class Role(QueryResourceManager):

    resource_type = 'aws.iam.role'


@resources.register('iam-user')
class User(QueryResourceManager):

    resource_type = 'aws.iam.user'


@resources.register('iam-policy')
class Policy(QueryResourceManager):

    resource_type = 'aws.iam.policy'


@resources.register('iam-profile')
class InstanceProfile(QueryResourceManager):

    resource_type = 'aws.iam.instance-profile'


@resources.register('iam-certificate')
class ServerCerficate(QueryResourceManager):

    resource_type = 'aws.iam.server-certificate'


