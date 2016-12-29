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
        id = 'Table'
        filter_name = None
        name = 'TableName'
        date = 'CreationDateTime'
        dimension = 'TableName'

    def augment(self, resources):
        def _augment(resource_set):
            client = local_session(self.session_factory).client('dynamodb')
            return [client.describe_table(TableName=r)['Table']
                    for r in resource_set]

        with self.executor_factory(max_workers=3) as w:
            return list(itertools.chain(
                *w.map(_augment, chunks(resources, 20))))


@Table.action_registry.register('delete')
class DeleteTable(BaseAction):
    """Action to delete dynamodb tables

    :example:

        .. code-block: yaml

            policies:
              - name: delete-tables
                resource: dynamodb-table
                actions:
                  - delete
    """

    schema = type_schema('delete')

    def delete_table(self, resource):
        print resource.get('TableName')
        client = local_session(self.manager.session_factory).client('dynamodb')
        client.delete_table(TableName=resource['TableName'])

    def process(self, resources):
        for r in resources:
            with self.executor_factory(max_workers=3) as w:
                futures = []
                futures.append(w.submit(self.delete_table, r))
                for f in as_completed(futures):
                    if f.exception():
                        self.log.error(
                            "Exception deleting dynamodb table \n %s" % (
                                f.exception()))
