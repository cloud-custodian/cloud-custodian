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

import itertools
import logging

from botocore.exceptions import ClientError

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import (type_schema, local_session)

log = logging.getLogger('custodian.rds-param-group')

pg_filters = FilterRegistry('rds-param-groups.filters')
pg_actions = ActionRegistry('rds-param-groups.actions')


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

    filter_registry = pg_filters
    action_registry = pg_actions


pg_cluster_filters = FilterRegistry('rds-cluster-param-groups.filters')
pg_cluster_actions = ActionRegistry('rds-cluster-param-groups.actions')


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

    filter_registry = pg_cluster_filters
    action_registry = pg_cluster_actions


class PGMixin(object):

    def get_pg_name(self, pg):
        return pg['DBParameterGroupName']


class PGClusterMixin(object):

    def get_pg_name(self, pg):
        return pg['DBClusterParameterGroupName']


class Copy(BaseAction):

    schema = type_schema(
        'copy',
        **{
            'required': ['name'],
            'name': {'type': 'string'},
            'description': {'type': 'string'},
        }
    )

    def process(self, param_groups):
        client = local_session(self.manager.session_factory).client('rds')

        for param_group in param_groups:
            name = self.get_pg_name(param_group)
            copy_name = self.data.get('name')
            copy_desc = self.data.get('description', 'Copy of {}'.format(name))
            try:
                self.do_copy(client, name, copy_name, copy_desc)
            except ClientError:
                # TODO - anything we need to catch?
                raise

            self.log.info('Copied RDS parameter group %s to %s', name, copy_name)


@pg_actions.register('copy')
class PGCopy(PGMixin, Copy):
    """ Action to copy an RDS parameter group.

    :example:

        .. code-block: yaml

            policies:
              - name: rds-param-group-copy
                resource: rds-param-group
                filters:
                  - DBParameterGroupName: original_pg_name
                actions:
                  - type: copy
                    name: copy_name
    """

    permissions = ('rds:CopyDBParameterGroup',)

    def do_copy(self, client, name, copy_name, desc):
        client.copy_db_parameter_group(
            SourceDBParameterGroupIdentifier=name,
            TargetDBParameterGroupIdentifier=copy_name,
            TargetDBParameterGroupDescription=desc
        )


@pg_cluster_actions.register('copy')
class ClusterCopy(PGClusterMixin, Copy):
    """ Action to copy an RDS cluster parameter group.

    :example:

        .. code-block: yaml

            policies:
              - name: rds-cluster-param-group-copy
                resource: rds-cluster-param-group
                filters:
                  - DBClusterParameterGroupName: original_pg_name
                actions:
                  - type: copy
                    name: copy_name
    """

    permissions = ('rds:CopyDBClusterParameterGroup',)

    def do_copy(self, client, name, copy_name, desc):
        client.copy_db_cluster_parameter_group(
            SourceDBClusterParameterGroupIdentifier=name,
            TargetDBClusterParameterGroupIdentifier=copy_name,
            TargetDBClusterParameterGroupDescription=desc
        )


class Delete(BaseAction):
    """Action to delete an RDS parameter group
    """

    schema = type_schema('delete')

    def process(self, param_groups):
        client = local_session(self.manager.session_factory).client('rds')

        for param_group in param_groups:
            name = self.get_pg_name(param_group)
            try:
                self.do_delete(client, name)
            except ClientError:
                # TODO - anything we need to catch?
                raise

            self.log.info('Deleted RDS parameter group: %s', name)


@pg_actions.register('delete')
class PGDelete(PGMixin, Delete):

    permissions = ('rds:DeleteDBParameterGroup',)

    def do_delete(self, client, name):
        client.delete_db_parameter_group(DBParameterGroupName=name)


@pg_cluster_actions.register('delete')
class ClusterDelete(PGClusterMixin, Delete):

    permissions = ('rds:DeleteDBClusterParameterGroup',)

    def do_delete(self, client, name):
        client.delete_db_cluster_parameter_group(DBClusterParameterGroupName=name)


class Modify(BaseAction):
    """Action to modify an RDS parameter group
    """

    schema = type_schema(
        'modify',
        **{
            'required': ['params'],
            'params': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'required': ['name', 'value'],
                    'name': {'type': 'string'},
                    'value': {'type': 'string'},
                    'apply-method': {'type': 'string', 'enum': ['immediate', 'pending-reboot']}
                },
            },
        }
    )

    def process(self, param_groups):
        client = local_session(self.manager.session_factory).client('rds')

        params = []
        for param in self.data.get('params', []):
            params.append({
                'ParameterName': param['name'],
                'ParameterValue': param['value'],
                'ApplyMethod': param.get('apply-method', 'immediate'),
            })

        # Can only do 20 elements at a time per docs, so if we have more than that we will
        # break it into multiple requests: https://goo.gl/Z6oGNv
        params = [iter(params)] * 20
        params = itertools.izip_longest(*params, fillvalue={})

        for param_set in params:
            for param_group in param_groups:
                name = self.get_pg_name(param_group)
                try:
                    self.do_modify(client, name, param_set)
                except ClientError:
                    # TODO - anything we need to catch?
                    raise

                self.log.info('Modified RDS parameter group: %s', name)


@pg_actions.register('modify')
class PGModify(PGMixin, Modify):

    permissions = ('rds:ModifyDBParameterGroup',)

    def do_modify(self, client, name, params):
        client.modify_db_parameter_group(DBParameterGroupName=name, Parameters=params)


@pg_cluster_actions.register('modify')
class ClusterModify(PGClusterMixin, Modify):
    """ Action to modify an RDS Cluster parameter group
    """

    permissions = ('rds:ModifyDBClusterParameterGroup',)

    def do_modify(self, client, name, params):
        client.modify_db_cluster_parameter_group(
            DBClusterParameterGroupName=name,
            Parameters=params
        )
