

from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('sns')
class SNS(QueryResourceManager):

    resource_type = 'aws.sns.topic'
