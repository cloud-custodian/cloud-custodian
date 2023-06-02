# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

import oci.config
from c7n_oci.filters.list import QueryFilter

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources, MaxResourceLimit, TypeInfo
from c7n.utils import local_session

log = logging.getLogger("custodian.oci.query")


class ResourceQuery:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.record_limit = 100

    def filter(self, resource_manager, client_name, operation, params):
        session = local_session(self.session_factory)
        client = session.client(client_name)

        return self._invoke_client_enum(client, operation, params)

    def _invoke_client_enum(self, client, operation, params):
        method = getattr(client, operation)
        response = oci.pagination.list_call_get_up_to_limit(
            method, **params, record_limit=self.record_limit, page_size=50
        )
        return response.data


@sources.register("describe-oci")
class DescribeSource:
    def __init__(self, manager):
        self.manager = manager
        self.query = ResourceQuery(manager.session_factory)

    def _get_search_details_model(self):
        query_filter = next(
            (f for f in self.manager.filters if isinstance(f, QueryFilter)), None
        )
        query = f"query {self.manager.resource_type.search_resource_type} resources return alladditionalfields"
        if query_filter and query_filter.data.get("params").get("compartment_id"):
            compartment_id = query_filter.data["params"]["compartment_id"]
            query += f" where compartmentId = '{compartment_id}'"
        return oci.resource_search.models.StructuredSearchDetails(
            type="Structured", query=query
        )

    def get_resources(self, query):
        params = {"search_details": self._get_search_details_model()}
        client_name = "oci.resource_search.ResourceSearchClient"
        operation = "search_resources"
        return self.query.filter(self.manager, client_name, operation, params)

    def augment(self, resources):
        return resources


class DescribeService(DescribeSource):
    def get_resources(self, query, params={}):
        client_name = (
            f"{self.manager.resource_type.service}.{self.manager.resource_type.client}"
        )
        operation, return_type, extra_args = self.manager.resource_type.enum_spec
        if self.manager.resource_type.enum_spec[-1]:
            params.update(self.manager.resource_type.enum_spec[-1])

        return self.query.filter(self.manager, client_name, operation, params)


class QueryMeta(type):
    """metaclass to have consistent action/filter registry for new resources."""

    def __new__(cls, name, parents, attrs):
        if "filter_registry" not in attrs:
            attrs["filter_registry"] = FilterRegistry("%s.filters" % name.lower())
        if "action_registry" not in attrs:
            attrs["action_registry"] = ActionRegistry("%s.actions" % name.lower())

        return super(QueryMeta, cls).__new__(cls, name, parents, attrs)


class QueryResourceManager(ResourceManager, metaclass=QueryMeta):
    type: str
    resource_type: "TypeInfo"

    source_mapping = sources

    def __init__(self, ctx, data):
        super(QueryResourceManager, self).__init__(ctx, data)
        self.source = self.get_source(self.source_type)

    def get_source(self, source_type):
        if source_type in self.source_mapping:
            return self.source_mapping.get(source_type)(self)
        if source_type in sources:
            return sources[source_type](self)
        raise KeyError("Invalid Source %s" % source_type)

    def get_client(self):
        return local_session(self.session_factory).client(
            f"{self.resource_type.service}.{self.resource_type.client}"
        )

    def get_model(self):
        return self.resource_type

    def get_resource(self, resource_info):
        return self.resource_type.get(self.get_client(), resource_info)

    @property
    def source_type(self):
        return self.data.get("source", "describe-oci")

    def get_resource_query(self):
        if "query" in self.data:
            return {"filter": self.data.get("query")}

    def resources(self, query=None):
        q = query or self.get_resource_query()
        resources = None
        result_resources = None
        if resources is None:
            with self.ctx.tracer.subsegment("resource-fetch"):
                result_resources = self._fetch_resources(q)
                resources = [
                    oci.util.to_dict(resource) for resource in result_resources
                ]

        resource_count = len(resources)
        with self.ctx.tracer.subsegment("filter"):
            resources = self.filter_resources(resources)

        # Check resource limits if we're the current policy execution.
        if self.data == self.ctx.policy.data:
            self.check_resource_limit(len(resources), resource_count)
        return resources

    def check_resource_limit(self, selection_count, population_count):
        """
        Check if policy's execution affects more resources then its limit.
        """
        p = self.ctx.policy
        max_resource_limits = MaxResourceLimit(p, selection_count, population_count)
        return max_resource_limits.check_resource_limits()

    def _fetch_resources(self, query):
        return self.augment(self.source.get_resources(query)) or []

    def augment(self, resources):
        return resources
