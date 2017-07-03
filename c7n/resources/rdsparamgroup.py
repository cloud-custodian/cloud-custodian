# Copyright 2017 Capital One Services, LLC
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

import logging

from botocore.exceptions import ClientError

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import (type_schema, local_session)

log = logging.getLogger('custodian.rds-param-group')

filters = FilterRegistry('rds-param-groups.filters')
actions = ActionRegistry('rds-param-groups.actions')


@resources.register('rds-param-group')
class RDSParamGroup(QueryResourceManager):
    """Resource manager for RDS parameter groups.
    """

    class resource_type(object):

        service = 'rds'
        type = 'pg'
        enum_spec = ('describe_db_parameter_groups', 'DBParameterGroups', None)
        name = id = 'DBParameterGroupName'
        filter_name = None
        filter_type = None
        dimension = 'DBParameterGroupName'
        date = None

    filter_registry = filters
    action_registry = actions


@resources.register('rds-cluster-param-group')
class RDSClusterParamGroup(QueryResourceManager):
    """ Resource manager for RDS cluster parameter groups.
    """
    
    class resource_type(object):

        service = 'rds'
        type = 'cluster-pg'
        enum_spec = ('describe_db_cluster_parameter_groups', 'DBClusterParameterGroups', None)
        name = id = 'DBClusterParameterGroupName'
        filter_name = None
        filter_type = None
        dimension = 'DBClusterParameterGroupName'
        date = None

    filter_registry = filters
    action_registry = actions


class PGMixin(object):

    def get_name(self, pg):
        return pg['DBParameterGroupName']


class PGClusterMixin(object):

    def get_name(self, pg):
        return pg['DBClusterParameterGroupName']


@actions.register('copy')
class Copy(PGMixin, BaseAction):
    """ Action to copy an RDS parameter group
    """

    schema = type_schema(
        'copy',
        **{
            'required': ['name'],
            'name': {'type': 'string'},
            'description': {'type': 'string'},
        }
    )

    permissions = ('rds:CopyDBParameterGroup',)
    
    def process(self, param_groups):
        client = local_session(self.manager.session_factory).client('rds')

        for param_group in param_groups:
            name = self.get_name(param_group)
            copy_name = self.data.get('name')
            copy_desc = self.data.get('description', 'Copy of {}'.format(name))
            try:
                self.do_copy(client, name, copy_name, copy_desc)
            except ClientError:
                # TODO - anything we need to catch?
                raise

            self.log.info('Copied RDS parameter group %s to %s', name, copy_name)

    def do_copy(self, client, name, copy_name, desc):
        client.copy_db_parameter_group(
            SourceDBParameterGroupIdentifier=name,
            TargetDBParameterGroupIdentifier=copy_name,
            TargetDBParameterGroupDescription=desc
        )


@actions.register('copy')
class ClusterCopy(PGClusterMixin, Copy):
    
    permissions = ('rds:CopyDBClusterParameterGroup')

    def do_copy(self, client, name, copy_name, desc):
        client.copy_db_parameter_group(
            SourceDBClusterParameterGroupIdentifier=name,
            TargetDBClusterParameterGroupIdentifier=copy_name,
            TargetDBClusterParameterGroupDescription=desc
        )


@actions.register('delete')
class Delete(PGMixin, BaseAction):
    """Action to delete an RDS parameter group
    """

    schema = type_schema('delete')
    permissions = ('rds:DeleteDBParameterGroup',)

    def process(self, param_groups):
        client = local_session(self.manager.session_factory).client('rds')

        for param_group in param_groups:
            name = self.get_name(param_group)
            try:
                self.do_delete(name)
            except ClientError:
                # TODO - anything we need to catch?
                raise

            self.log.info('Deleted RDS parameter group: %s', name)

    def do_delete(self, name):
        client.delete_db_parameter_group(DBParameterGroupName=name)


@actions.register('delete')
class ClusterDelete(Delete):
    
    permissions = ('rds:DeleteDBClusterParameterGroup',)

    def do_delete(self):
        client.delete_db_cluster_parameter_group(DBClusterParameterGroupName=name)
        

@actions.register('modify')
class Modify(PGMixin, BaseAction):
    """Action to modify an RDS parameter group
    """

    schema = type_schema(
        'modify',
        **{
            'required': [],
        }
    )
    permissions = ('rds:ModifyDBParameterGroup',)

    def process(self, param_groups):
        client = local_session(self.manager.session_factory).client('rds')

        for param_group in param_groups:
            name = self.get_name(param_group)
            try:
                self.do_modify(name)
            except ClientError:
                # TODO - anything we need to catch?
                raise

            self.log.info('Modified RDS parameter group: %s', name)

    def do_modify(self, name):
        pass
        #client.modify_db_parameter_group(DBParameterGroupName=name)


@actions.register('modify')
class ClusterModify(PGClusterMixin, Modify):
    """ Action to modify an RDS Cluster parameter group
    """

    permissions = ('rds:ModifyDBClusterParameterGroup',)

    def do_modify(name):
        pass
