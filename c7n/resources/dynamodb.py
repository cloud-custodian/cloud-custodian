import itertools

from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import chunks, local_session


@resources.register('dynamodb-table')
class Table(QueryResourceManager):

    resource_type = 'aws.dynamodb.table'

    def augment(self, resources):

        def _augment(resource_set):
            client = local_session(self.session_factory).client('dynamodb')
            return [client.describe_table(TableName=r)['Table']
                    for r in resource_set]

        with self.executor_factory(max_workers=3) as w:
            return list(itertools.chain(
                *w.map(_augment, chunks(resources, 20))))
