from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('rest-api')
class RestAPI(QueryResourceManager):

    resource_type = "aws.apigateway.restapis"

