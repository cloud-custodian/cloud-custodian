# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

import oci.config

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources, MaxResourceLimit, TypeInfo
from c7n.utils import local_session
from c7n_oci.constants import COMPARTMENT_IDS, STORAGE_NAMESPACE

log = logging.getLogger("custodian.oci.query")


class ResourceQuery:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def filter(self, resource_manager, client_name, operation, params):
        session = local_session(self.session_factory)
        client = session.client(client_name)

        return self._invoke_client_enum(client, operation, params)

    def _invoke_client_enum(self, client, operation, params):
        method = getattr(client, operation)
        response = oci.pagination.list_call_get_all_results(method, **params)
        return response.data


@sources.register("describe-native")
class DescribeSource:
    def __init__(self, manager):
        self.manager = manager
        self.query = ResourceQuery(manager.session_factory)

    def get_resources(self, query):
        resources = None
        if "query" in self.manager.data and COMPARTMENT_IDS in list(
            map(lambda x: list(x.keys())[0], self.manager.data.get("query"))
        ):
            resources = self._get_resources_for_list_of_compartment_ids(
                self._get_list_of_compartment_ids_from_query(),
                self._construct_list_func_ref(),
            )
        return resources

    def _get_resources_for_list_of_compartment_ids(self, compartment_ids, list_func_ref):
        resources = []
        for compartment_id in compartment_ids:
            results = self._get_resources_with_compartment_and_params(compartment_id, list_func_ref)
            for result in results:
                resources.append(oci.util.to_dict(result))
        return resources

    def _get_list_of_compartment_ids_from_query(self):
        if "query" in self.manager.data:
            compartment_ids = []
            for query_dict in self.manager.data.get("query"):
                for k, v in query_dict.items():
                    if k == COMPARTMENT_IDS:
                        for compartment_id in v:
                            compartment_ids.append(compartment_id)
            return compartment_ids
        return None

    def _construct_list_func_ref(self):
        operation, return_type, extra_args = self.manager.resource_type.enum_spec
        return getattr(self.manager.get_client(), operation)

    def _get_resources_with_compartment_and_params(self, compartment_id, list_func_ref):
        kw = self._get_fields_from_query_except_compartment()
        if (
            self.manager._get_extra_params().get(STORAGE_NAMESPACE) is not None
            and kw.get(STORAGE_NAMESPACE) is None
        ):
            kw[STORAGE_NAMESPACE] = self.manager._get_extra_params()[STORAGE_NAMESPACE]
        kw["compartment_id"] = compartment_id
        return oci.pagination.list_call_get_all_results(list_func_ref, **kw).data

    def _get_fields_from_query_except_compartment(self):
        kw = {}
        if self.manager.resource_type.enum_spec[2] is not None:
            kw = {**self.manager.resource_type.enum_spec[2]}
        if "query" in self.manager.data:
            for query_dict in self.manager.data.get("query"):
                for k, v in query_dict.items():
                    if not k == COMPARTMENT_IDS:
                        kw[k] = v
            return kw
        return {}

    def augment(self, resources):
        return resources


@sources.register("describe-search")
class DescribeSearch(DescribeSource):
    def __init__(self, manager):
        self.manager = manager
        self.query = ResourceQuery(manager.session_factory)

    def get_resources(self, query):
        params = {
            "search_details": self._get_search_details_model(
                self._get_param("compartment_id", query)
            )
        }
        # params = {**params, **self._get_query_params(query)}
        client_name = "oci.resource_search.ResourceSearchClient"
        operation = "search_resources"
        resources = self.query.filter(self.manager, client_name, operation, params)
        compartment_ids = set()
        for resource in resources:
            compartment_ids.add(resource.compartment_id)
        fetched_resources = self._get_resources_for_list_of_compartment_ids(
            compartment_ids, self._construct_list_func_ref()
        )
        return fetched_resources

    def _get_search_details_model(self, compartment_id):
        query = f"query {self.manager.resource_type.search_resource_type} resources"
        return oci.resource_search.models.StructuredSearchDetails(type="Structured", query=query)

    def _get_param(self, param_name, query):
        if query is None:
            return None
        params = query.get("filter")
        for index in range(len(params)):
            param = params[index]
            if param_name in param:
                return param.get(param_name)
        return None

    # Contruct the query params by skipping the compartment_id as it used for building
    # the search model
    def _get_query_params(self, query):
        if query is None:
            return {}
        selected_params = {}
        params = query.get("filter")
        for index in range(len(query.get("filter"))):
            param = params[index]
            if "compartment_ids" not in param:
                selected_params = {**selected_params, **param}
        return selected_params

    def augment(self, resources):
        return resources


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

    def _construct_list_func_ref(self):
        operation, return_type, extra_args = self.resource_type.enum_spec
        return getattr(self.get_client(), operation)

    def get_session(self):
        return local_session(self.session_factory)

    def get_model(self):
        return self.resource_type

    def get_resource(self, resource_info):
        return self.resource_type.get(self.get_client(), resource_info)

    @property
    def source_type(self):
        if "query" in self.data and COMPARTMENT_IDS in list(
            map(lambda x: list(x.keys())[0], self.data.get("query"))
        ):
            return "describe-native"
        else:
            return "describe-search"

    def get_resource_query(self):
        if "query" in self.data:
            return {"filter": self.data.get("query")}

    def resources(self, query=None):
        q = query or self.get_resource_query()
        resources = {}
        with self.ctx.tracer.subsegment("resource-fetch"):
            resources = self._fetch_resources(q)
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

    def _get_extra_params(self):
        return {}
