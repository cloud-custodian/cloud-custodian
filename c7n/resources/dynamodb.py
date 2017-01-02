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
import itertools

from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import chunks, local_session, type_schema
from c7n.actions import BaseAction

from concurrent.futures import as_completed


@resources.register('dynamodb-table')
class Table(QueryResourceManager):

    class resource_type(object):
        service = 'dynamodb'
        type = 'table'
        enum_spec = ('list_tables', 'TableNames', None)
        detail_spec = ("describe_table", "TableName", None, "Table")
        id = 'Table'
        filter_name = None
        name = 'TableName'
        date = 'CreationDateTime'
        dimension = 'TableName'


class StatusFilter(object):
    """Filter tables by status"""

    valid_states = ()

    def filter_table_state(self, tables, states=None):
        states = states or self.valid_states
        orig_count = len(tables)
        result = [t for t in tables if t['TableStatus'] in states]
        self.log.info("%s %d of %d tables" % (
            self.__class__.__name__, len(result), orig_count))
        return result


@Table.action_registry.register('delete')
class DeleteTable(BaseAction, StatusFilter):
    """Action to delete dynamodb tables

    :example:

        .. code-block: yaml

            policies:
              - name: delete-empty-tables
                resource: dynamodb-table
                filters:
                  - TableSizeBytes: 0
                actions:
                  - delete
    """

    valid_status = ('ACTIVE',)
    schema = type_schema('delete')

    def delete_table(self, table_set):
        client = local_session(self.manager.session_factory).client('dynamodb')
        for t in table_set:
            client.delete_table(TableName=t['TableName'])

    def process(self, resources):
        resources = self.filter_table_state(
            resources, self.valid_status)
        if not len(resources):
            return

        for table_set in chunks(resources, 20):
            with self.executor_factory(max_workers=3) as w:
                futures = []
                futures.append(w.submit(self.delete_table, table_set))
                for f in as_completed(futures):
                    if f.exception():
                        self.log.error(
                            "Exception deleting dynamodb table set \n %s" % (
                                f.exception()))
