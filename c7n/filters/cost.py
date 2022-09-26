import os

from c7n.cache import NullCache
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport

from .core import OPERATORS, Filter


class Cost(Filter):
    """Annotate resource monthly cost with Infracost pricing API.
    It aims to provide an approximate cost for a generic case. For example,
    it only grabs the on-demand price with no pre-installed software for EC2 instances.

    Please use INFRACOST_API_ENDPOINT and INFRACOST_API_KEY environment vars
    to specify the API config.

    .. code-block:: yaml

    policies:
      - name: ec2-cost
        resource: ec2
        filters:
          - type: cost
            op: greater-than
            # USD
            value: 4
            # monthly price = unit price * 730 hours
            quantity: 730


    reference: https://www.infracost.io/docs/cloud_pricing_api/overview/
    """

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'required': ['type'],
        'properties': {
            'api_endpoint': {'type': 'string'},
            'api_key': {'type': 'string'},
            # 'currency': {'type': 'number'},
            'quantity': {'type': 'number'},
            'op': {'$ref': '#/definitions/filters_common/comparison_operators'},
            'type': {'enum': ['cost']},
            'value': {'type': 'number'},
        },
    }
    schema_alias = True
    ANNOTATION_KEY = "c7n:Cost"

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.cache = manager._cache or NullCache({})
        self.api_endpoint = data.get(
            "api_endpoint",
            os.environ.get("INFRACOST_API_ENDPOINT", "https://pricing.api.infracost.io"),
        )
        self.api_key = data.get("api_key", os.environ.get("INFRACOST_API_KEY"))

    def get_permissions(self):
        return ("ec2:DescribeInstances",)

    def validate(self):
        name = self.__class__.__name__
        if self.api_endpoint is None:
            raise ValueError("%s Filter requires Infracost pricing_api_endpoint" % name)

        if self.api_key is None:
            raise ValueError("%s Filter requires Infracost api_key" % name)
        return super(Cost, self).validate()

    def process_resource(self, resource, client, query):
        price = self.get_price(resource, client, query)
        op = self.data.get('operator', 'ge')
        value = self.data.get('value', -1)
        return OPERATORS[op](price["USD"], value)

    def get_price(self, resource, client, query):
        params = self.get_params(resource)
        cache_key = str(params)

        with self.cache:
            price = self.cache.get(cache_key)
            if not price:
                price = self.get_infracost(client, query, params)
                # TODO support configurable currency
                price["USD"] = float(price["USD"]) * self.data.get("quantity", 1)
                self.cache.save(cache_key, price)

        resource[self.ANNOTATION_KEY] = price
        return price

    def get_infracost(self, client, query, params):
        result = client.execute(query, variable_values=params)
        self.log.info(f"Infracost {params}: {result}")
        total = len(result["products"][0]["prices"])
        if total > 1:
            self.log.warning(f"Found {total} price options, expecting 1")
        return result["products"][0]["prices"][0]

    def process(self, resources, event=None):
        transport = RequestsHTTPTransport(
            url=self.api_endpoint + "/graphql",
            headers={'X-Api-Key': self.api_key},
            verify=True,
            retries=5,
        )
        client = Client(transport=transport, fetch_schema_from_transport=True)
        query = gql(self.get_query())
        return [r for r in resources if self.process_resource(r, client, query)]

    def get_query(self):
        raise NotImplementedError("use subclass")

    def get_params(self, resource):
        raise NotImplementedError("use subclass")
