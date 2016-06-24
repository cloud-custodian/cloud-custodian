
from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('firehose')
class DeliveryStream(QueryResourceManager):

    resource_type = "aws.firehose.deliverystream"

