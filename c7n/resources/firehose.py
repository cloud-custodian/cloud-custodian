
from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('firehose')
class DeliveryStream(QueryResourceManager):

    rseource_type = "aws.firehose.deliverystream"

