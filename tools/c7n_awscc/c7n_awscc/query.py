import json

from botocore.exceptions import ClientError
from botocore.paginate import Paginator
import jmespath

from c7n.query import RetryPageIterator
from c7n.utils import local_session


class CloudControl:

    resources_expr = jmespath.compile("ResourceDescriptions[].Properties")

    def __init__(self, manager):
        self.manager = manager

    def get_permissions(self):
        # cfn type registry implementations use undefined permission
        # sets that only are discoverable at runtime :/
        return []

    def get_query_params(self, query_params):
        # nothing useful exposed for resource filtering
        return query_params

    def _get_resource_paginator(self, client):
        p = Paginator(
            client.list_resources,
            {
                "input_token": "NextToken",
                "output_token": "NextToken",
                "result_key": "ResourceDescriptions",
            },
            client.meta.service_model.operation_model("ListResources"),
        )
        p.PAGE_ITERATOR_CLS = RetryPageIterator
        return p

    def resources(self, query):
        client = local_session(self.manager.session_factory).client("cloudcontrol")
        p = self._get_resource_paginator(client)
        results = self.resources_expr.search(
            p.paginate(TypeName=self.manager.resource_type.cfn_type).build_full_result()
        )
        # properties are serialized json, in json.. yo dawg :/
        results = list(map(json.loads, results))
        return results

    def get_resources(self, ids, cache=True):
        client = local_session(self.manager.session_factory).client("cloudcontrol")
        resources = []
        for i in ids:
            try:
                r = client.get_resource(
                    TypeName=self.manager.resource_type.cfn_type, Identifier=i
                )["ResourceDescription"]["Properties"]
                resources.append(json.loads(r))
            except ClientError:
                continue
        return resources

    def augment(self, resources):
        # nothing useful to do, most types via this control
        # include tags.
        return resources
