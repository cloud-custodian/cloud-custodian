

from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('table')
class Table(QueryResourceManager):

    resource_type = 'aws.dynamodb.table'
