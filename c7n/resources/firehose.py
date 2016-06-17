
from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register
class KinesisStream(QueryResourceManager):

    rseource_type = "aws.kinesis.stream"

