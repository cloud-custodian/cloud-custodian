

from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('alarm')
class Alarm(QueryResourceManager):

    resource_type = 'aws.sns.Alarm'


