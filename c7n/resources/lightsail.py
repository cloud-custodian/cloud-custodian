# Copyright 2018 Capital One Services, LLC
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
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo


@resources.register('lightsail-instance')
class Instance(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'lightsail'
        enum_spec = ('get_instances', 'instances', None)
        arn = id = 'arn'
        name = 'name'
        date = 'createdAt'


@resources.register('lightsail-db')
class Database(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'lightsail'
        enum_spec = ('get_relational_databases', 'relationalDatabases', None)
        name = 'name'
        arn = id = 'arn'
        date = 'createdAt'


@resources.register('lightsail-elb')
class LoadBalancer(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'lightsail'
        enum_spec = ('get_load_balancers', 'loadBalancers', None)
        name = 'name'
        arn = id = 'arn'
        date = 'createdAt'
