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


@actions.register('delete')
class Delete(BaseAction):
    """Action to delete an RDS parameter group
    """

    schema = type_schema('delete')
    permissions = ('rds:DeleteDBParameterGroup',)

    def process(self, param_groups):
        client = local_session(self.manager.session_factory).client('rds')

        for param_group in param_groups:
            name = param_group['DBParameterGroupName']
            try:
                client.delete_db_parameter_group(DBParameterGroupName=name)
            except ClientError:
                # TODO - anything we need to catch?
                raise

            self.log.info('Deleted RDS parameter group: %s', name)
