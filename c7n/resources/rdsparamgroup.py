# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import itertools

from botocore.exceptions import ClientError

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry, ValueFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import (type_schema, local_session, chunks)
from c7n.tags import universal_augment

log = logging.getLogger('custodian.rds-param-group')

pg_filters = FilterRegistry('rds-param-group.filters')
pg_actions = ActionRegistry('rds-param-group.actions')


@resources.register('rds-param-group')
class RDSParamGroup(QueryResourceManager):
    """Resource manager for RDS parameter groups.
    """

    class resource_type(TypeInfo):

        service = 'rds'
        arn_type = 'pg'
        enum_spec = ('describe_db_parameter_groups', 'DBParameterGroups', None)
        name = id = 'DBParameterGroupName'
        arn = 'DBParameterGroupArn'
        dimension = 'DBParameterGroupName'
        permissions_enum = ('rds:DescribeDBParameterGroups',)
        cfn_type = 'AWS::RDS::DBParameterGroup'
        universal_taggable = object()
        permissions_augment = ("rds:ListTagsForResource",)

    augment = universal_augment

    filter_registry = pg_filters
    action_registry = pg_actions


pg_cluster_filters = FilterRegistry('rds-cluster-param-group.filters')
pg_cluster_actions = ActionRegistry('rds-cluster-param-group.actions')


@pg_filters.register('db-parameter')
class ParameterFilter(ValueFilter):
    """
    Applies value type filter on set db parameter values.
    :example:

    .. code-block:: yaml

            policies:
              - name: rds-pg
                resource: rds
                filters:
                  - type: db-parameter
                    key: someparam
                    op: eq
                    value: someval
    """

    schema = type_schema('db-parameter', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('rds:DescribeDBParameters')
    policy_annotation = 'c7n:MatchedDBParameter'

    @staticmethod
    def recast(val, datatype):
        """ Re-cast the value based upon an AWS supplied datatype
            and treat nulls sensibly.
        """
        ret_val = val
        if datatype == 'string':
            ret_val = str(val)
        elif datatype == 'boolean':
            # AWS returns 1s and 0s for boolean for most of the cases
            if val.isdigit():
                ret_val = bool(int(val))
            # AWS returns 'TRUE,FALSE' for Oracle engine
            elif val == 'TRUE':
                ret_val = True
            elif val == 'FALSE':
                ret_val = False
        elif datatype == 'integer':
            if val.isdigit():
                ret_val = int(val)
        elif datatype == 'float':
            ret_val = float(val) if val else 0.0

        return ret_val
    
    def _get_param_list(self, pg):
        client = local_session(self.manager.session_factory).client('rds')
        paginator = client.get_paginator('describe_db_parameters')
        param_list = list(itertools.chain(*[p['Parameters']
            for p in paginator.paginate(DBParameterGroupName=pg)]))
        print(param_list)
        return param_list

    def get_pg_values(self, param_group):
        pgvalues = {}
        param_list = self._get_param_list(param_group)
        pgvalues = {
            p['ParameterName']: self.recast(p['ParameterValue'], p['DataType'])
            for p in param_list if 'ParameterValue' in p}
        return pgvalues

    def process(self, resources, event=None):
        results = []
        for resource in resources:
            pg_values = self.get_pg_values(resource['DBParameterGroupName'])
            print("{} .... {} ... {}".format(resource['DBParameterGroupName'], pg_values.get('require_secure_transport'), pg_values.get('tls_version')))
            if self.match(pg_values):
                resource.setdefault(self.policy_annotation, []).append(
                    self.data.get('key'))
                results.append(resource)

        return results

@resources.register('rds-cluster-param-group')
class RDSClusterParamGroup(QueryResourceManager):
    """ Resource manager for RDS cluster parameter groups.
    """

    class resource_type(TypeInfo):

        service = 'rds'
        arn_type = 'cluster-pg'
        arn = 'DBClusterParameterGroupArn'
        enum_spec = ('describe_db_cluster_parameter_groups', 'DBClusterParameterGroups', None)
        name = id = 'DBClusterParameterGroupName'
        dimension = 'DBClusterParameterGroupName'
        permissions_enum = ('rds:DescribeDBClusterParameterGroups',)
        cfn_type = 'AWS::RDS::DBClusterParameterGroup'
        universal_taggable = object()

    augment = universal_augment

    filter_registry = pg_cluster_filters
    action_registry = pg_cluster_actions


class PGMixin:

    def get_pg_name(self, pg):
        return pg['DBParameterGroupName']


class PGClusterMixin:

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
            self.do_copy(client, name, copy_name, copy_desc)
            self.log.info('Copied RDS parameter group %s to %s', name, copy_name)


@pg_actions.register('copy')
class PGCopy(PGMixin, Copy):
    """ Action to copy an RDS parameter group.

    :example:

    .. code-block:: yaml

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
class PGClusterCopy(PGClusterMixin, Copy):
    """ Action to copy an RDS cluster parameter group.

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-param-group-copy
                resource: rds-cluster-param-group
                filters:
                  - DBClusterParameterGroupName: original_cluster_pg_name
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

    schema = type_schema('delete')

    def process(self, param_groups):
        client = local_session(self.manager.session_factory).client('rds')

        for param_group in param_groups:
            name = self.get_pg_name(param_group)
            try:
                self.do_delete(client, name)
            except ClientError as e:
                if e.response['Error']['Code'] == 'DBParameterGroupNotFoundFault':
                    self.log.warning('RDS parameter group %s already deleted', name)
                    continue
                raise
            self.log.info('Deleted RDS parameter group: %s', name)


@pg_actions.register('delete')
class PGDelete(PGMixin, Delete):
    """Action to delete an RDS parameter group

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-param-group-delete
                resource: rds-param-group
                filters:
                  - DBParameterGroupName: pg_name
                actions:
                  - type: delete
    """

    permissions = ('rds:DeleteDBParameterGroup',)

    def do_delete(self, client, name):
        client.delete_db_parameter_group(DBParameterGroupName=name)


@pg_cluster_actions.register('delete')
class PGClusterDelete(PGClusterMixin, Delete):
    """Action to delete an RDS cluster parameter group

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-param-group-delete
                resource: rds-cluster-param-group
                filters:
                  - DBClusterParameterGroupName: cluster_pg_name
                actions:
                  - type: delete
    """

    permissions = ('rds:DeleteDBClusterParameterGroup',)

    def do_delete(self, client, name):
        client.delete_db_cluster_parameter_group(DBClusterParameterGroupName=name)


class Modify(BaseAction):

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

        for param_group in param_groups:
            name = self.get_pg_name(param_group)

            # Fetch the existing parameters for this DB, so we only try to change the ones that are
            # different.
            cur_params = self.get_current_params(client, name)
            changed_params = []
            for param in params:
                param_name = param['ParameterName']
                if (param_name not in cur_params or
                   cur_params[param_name]['ParameterValue'] != param['ParameterValue']):
                    changed_params.append(param)

            # Can only do 20 elements at a time per docs, so if we have more than that we will
            # break it into multiple requests:
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/rds.html#RDS.Client.modify_db_parameter_group
            for param_set in chunks(changed_params, 5):
                self.do_modify(client, name, param_set)

            self.log.info('Modified RDS parameter group %s (%i parameters changed, %i unchanged)',
                          name, len(changed_params), len(params) - len(changed_params))


@pg_actions.register('modify')
class PGModify(PGMixin, Modify):
    """Action to modify an RDS parameter group

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-param-group-modify
                resource: rds-param-group
                filters:
                  - DBParameterGroupName: pg_name
                actions:
                  - type: modify
                    params:
                    - name: autocommit
                      value: "1"
                    - name: max_connections
                      value: "100"
    """

    permissions = ('rds:DescribeDBParameters', 'rds:ModifyDBParameterGroup')

    def get_current_params(self, client, name):
        params = client.describe_db_parameters(DBParameterGroupName=name)
        return {x['ParameterName']: {
                'ParameterValue': x.get('ParameterValue'),
                'ApplyMethod': x['ApplyMethod']}
                for x in params.get('Parameters', [])}

    def do_modify(self, client, name, params):
        client.modify_db_parameter_group(DBParameterGroupName=name, Parameters=params)


@pg_cluster_actions.register('modify')
class PGClusterModify(PGClusterMixin, Modify):
    """Action to modify an RDS cluster parameter group

    :example:

    .. code-block:: yaml

            policies:
              - name: rds-cluster-param-group-modify
                resource: rds-cluster-param-group
                filters:
                  - DBClusterParameterGroupName: cluster_pg_name
                actions:
                  - type: modify
                    params:
                    - name: lower_case_table_names
                      value: "1"
                    - name: master_verify_checksum
                      value: "1"
    """

    permissions = ('rds:DescribeDBClusterParameters', 'rds:ModifyDBClusterParameterGroup')

    def get_current_params(self, client, name):
        params = client.describe_db_cluster_parameters(DBClusterParameterGroupName=name)
        return {x['ParameterName']: {
                'ParameterValue': x.get('ParameterValue'),
                'ApplyMethod': x['ApplyMethod']}
                for x in params.get('Parameters', [])}

    def do_modify(self, client, name, params):
        client.modify_db_cluster_parameter_group(
            DBClusterParameterGroupName=name,
            Parameters=params
        )
