

from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('sqs')
class SQS(QueryResourceManager):

    resource_type = 'aws.sqs.queue'
