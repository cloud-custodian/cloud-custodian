from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('lambda')
class AWSLambda(QueryResourceManager):

    resource_type = "aws.lambda.function"
