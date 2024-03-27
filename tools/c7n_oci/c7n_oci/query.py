# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import os

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
        session = resource_manager.get_session()
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
        compartment_ids = self._get_list_of_compartment_ids()
        log.debug(
            f"List of compartment IDs fetched using the environment variable ${COMPARTMENT_IDS}:"
            f" {compartment_ids}"
        )
        resources = self._get_resources_for_list_of_compartment_ids(
            compartment_ids,
            self._construct_list_func_ref(),
        )
        return resources

    def _get_resources_for_list_of_compartment_ids(self, compartment_ids, list_func_ref):
        resources = []
        for compartment_id in compartment_ids:
            cache_key = self.get_cache_key_for_compartment(compartment_id)
            cached_resources = self.manager._cache.get(cache_key)
            if cached_resources:
                self.manager.log.debug(
                    "Using cached oci.%s: %d",
                    self.manager.type,
                    len(cached_resources),
                )
                resources.extend(cached_resources)
            else:
                results = self._get_resources_with_compartment_and_params(
                    compartment_id, list_func_ref
                )
                cache_results = []
                for result in results:
                    resource = oci.util.to_dict(result)
                    resources.append(resource)
                    cache_results.append(resource)
                self.manager._cache.save(cache_key, cache_results)
        return resources

    @staticmethod
    def _get_list_of_compartment_ids():
        comps_env_var = os.environ.get(COMPARTMENT_IDS).split(",")
        return [comp.strip() for comp in comps_env_var if comp and comp.strip()]

    def _construct_list_func_ref(self):
        operation, _, _ = self.manager.resource_type.enum_spec
        return getattr(self.manager.get_client(), operation)

    def _get_resources_with_compartment_and_params(self, compartment_id, list_func_ref):
        kw = self._get_fields_from_query()
        if (
            self.manager._get_extra_params().get(STORAGE_NAMESPACE) is not None
            and kw.get(STORAGE_NAMESPACE) is None
        ):
            kw[STORAGE_NAMESPACE] = self.manager._get_extra_params()[STORAGE_NAMESPACE]
        kw["compartment_id"] = compartment_id
        return oci.pagination.list_call_get_all_results(list_func_ref, **kw).data

    def _get_fields_from_query(self):
        kw = {}
        if self.manager.resource_type.enum_spec[2] is not None:
            kw = {**self.manager.resource_type.enum_spec[2]}
        if "query" in self.manager.data:
            for query_dict in self.manager.data.get("query"):
                for k, v in query_dict.items():
                    kw[k] = v
            return kw
        return kw

    def augment(self, resources):
        return resources

    def get_cache_key_for_compartment(self, compartment_id):
        return {
            'tenancy': self.manager.session_factory.config.get('tenancy'),
            'region': self.manager.session_factory.config.get('region'),
            'resource': self.manager.resource_type.resource_type,
            'compartment_id': compartment_id,
            'q': self.manager.data.get('query'),
        }


@sources.register("describe-search")
class DescribeSearch(DescribeSource):
    def __init__(self, manager):
        self.manager = manager
        self.query = ResourceQuery(manager.session_factory)

    def get_resources(self, query):
        params = {"search_details": self._get_search_details_model()}
        client_name = "oci.resource_search.ResourceSearchClient"
        operation = "search_resources"
        resources = []
        cache_key = self.get_cache_key_for_search()
        cached_resources = self.manager._cache.get(cache_key)
        if cached_resources:
            self.manager.log.debug(
                "Using cached oci.%s: %d",
                self.manager.type,
                len(cached_resources),
            )
            resources.extend(cached_resources)
        else:
            resources = self.query.filter(self.manager, client_name, operation, params)
            self.manager._cache.save(cache_key, resources)
        compartment_ids = set()
        for resource in resources:
            compartment_ids.add(resource.compartment_id)
        log.info(
            f"List of compartment IDs fetched using the ResourceSearchClient: {compartment_ids}"
        )
        fetched_resources = self._get_resources_for_list_of_compartment_ids(
            compartment_ids, self._construct_list_func_ref()
        )
        return fetched_resources

    def _get_search_details_model(self):
        query = f"query {self.manager.resource_type.search_resource_type} resources"
        return oci.resource_search.models.StructuredSearchDetails(type="Structured", query=query)

    # Contruct the query params as it used for building the search model
    def _get_query_params(self, query):
        if query is None or query.get("filter") is None:
            return {}
        return {**query.get("filter")}

    def augment(self, resources):
        return resources

    def get_cache_key_for_search(self):
        return {
            'tenancy': self.manager.session_factory.config.get('tenancy'),
            'region': self.manager.session_factory.config.get('region'),
            'resource': self.manager.resource_type.resource_type,
            'q': self.manager.data.get('query'),
        }


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
        return self.get_session().client(
            f"{self.resource_type.service}.{self.resource_type.client}"
        )

    def _construct_list_func_ref(self):
        operation, _, _ = self.resource_type.enum_spec
        return getattr(self.get_client(), operation)

    # Get the session object for the respective region
    def get_session(self):
        return local_session(self.session_factory, self.config.get("region"))

    def get_model(self):
        return self.resource_type

    def get_resource(self, resource_info):
        return self.resource_type.get(self.get_client(), resource_info)

    @property
    def source_type(self):
        if os.environ.get(COMPARTMENT_IDS) is not None:
            return "describe-native"
        else:
            return "describe-search"

    def get_resource_query(self):
        if "query" in self.data:
            return {"filter": self.data.get("query")}

    def resources(self, query=None):
        q = query or self.get_resource_query()
        resources = {}
        self._cache.load()
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
        Check if policy's execution affects more resources than its limit.
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
