# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
