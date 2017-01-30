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
import functools
import itertools

from botocore.exceptions import ClientError
from c7n.filters import FilterRegistry, AgeFilter, OPERATORS
from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import chunks, local_session, type_schema
from c7n.actions import BaseAction
from c7n.utils import (
    local_session, get_account_id, generate_arn,
    get_retry, chunks, snapshot_identifier, type_schema)

from concurrent.futures import as_completed

filters = FilterRegistry('dynamodb-table.filters')

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

    filter_registry = filters
    _generate_arn = _account_id = None
    retry = staticmethod(get_retry(('Throttled',)))
    #permissions = ('dynamodb:ListTagsOfResource')
    
    @property
    def account_id(self):
        if self._account_id is None:
            session = local_session(self.session_factory)
            self._account_id = get_account_id(session)
        return self._account_id
    
    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                'dynamodb',
                region=self.config.region,
                account_id=self.account_id,
                separator=':')
        return self._generate_arn
    
    def augment(self, tables):
        filter(None, _dynamodb_table_tags(
            self.get_model(),
            tables, self.session_factory, self.executor_factory,
            self.generate_arn, self.retry))
        return tables


def _dynamodb_table_tags(
        model, tables, session_factory, executor_factory, generator, retry):
    """ Augment DynamoDB tables with their respective tags
    """

    def process_tags(table):
        client = local_session(session_factory).client('dynamodb')
        arn = generator(table)
        tag_list = None
        try:
            tag_list = retry(
                client.list_tags_of_resource,
                ResourceArn=arn)['Tags']
        except ClientError as e:
            log.warning("Exception getting DynamoDB tags  \n %s", e)
            return None

        table['Tags'] = tag_list
        return table

    with executor_factory(max_workers=1) as w:
        return list(w.map(process_tags, tables))
    
    
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
    permissions = ("dynamodb:DeleteTable",)

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


@resources.register('dynamodb-stream')
class Stream(QueryResourceManager):

    # Note stream management takes place on the table resource

    class resource_type(object):
        service = 'dynamodbstreams'
        # Note max rate of 5 calls per second
        enum_spec = ('list_streams', 'Streams', None)
        # Note max rate of 10 calls per second.
        detail_spec = (
            "describe_stream", "StreamArn", "StreamArn", "StreamDescription")
        id = 'StreamArn'

        # TODO, we default to filtering by id, but the api takes table names, which
        # require additional client side filtering as multiple streams may be present
        # per table.
        # filter_name = 'TableName'
        filter_name = None

        name = 'TableName'
        date = 'CreationDateTime'
        dimension = 'TableName'
