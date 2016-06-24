
from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('kinesis')
class KinesisStream(QueryResourceManager):

    resource_type = "aws.kinesis.stream"

