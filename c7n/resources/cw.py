

from c7n.query import QueryResourceManager
from c7n.manager import resources


@resources.register('alarm')
class Alarm(QueryResourceManager):

    resource_type = 'aws.cloudwatch.alarm'


@resources.register('log-group')
class LogGroup(QueryResourceManager):

    class Meta(object):

        service = 'logs'
        type = 'log-group'
        enum_spec = ('describe_log_groups', 'logGroups', None)

        name = 'logGroupName'
        id = 'arn'
        filter_name = 'logGroupNamePrefix'
        filter_type = 'scalar'
        dimension = 'LogGroupName'
        date = 'creationTime'

    resource_type = Meta
