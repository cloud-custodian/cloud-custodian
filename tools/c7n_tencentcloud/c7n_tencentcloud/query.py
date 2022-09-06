# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import jmespath
from .client import Session
from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources


class TypeMeta(type):
    def __repr__(self) -> str:
        return ""


class ResourceTypeInfo(metaclass=TypeMeta):
    # used to construct tencentcloud client
    endpoint = None  #
    service = None  #
    version = None  #

    # enum_spec: ("action", "jsonpath", "extra_params")
    enum_spec = ()


class ResourceQuery:
    """ResourceQuery"""
    def __init__(self, session_factory: Session) -> None:
        self.session_factory = session_factory

    def filter(self, resource_manager, params: dict):
        resource_type: ResourceTypeInfo = resource_manager.resource_type
        region = "ap-singapore"

        cli = self.session_factory.client(resource_type.endpoint,
                                          resource_type.service,
                                          resource_type.version,
                                          region)
        action, jsonpath, extra_params = resource_type.enum_spec
        if extra_params:
            params.update(extra_params)

        resp = cli.execute_query(action, params)
        return jmespath.search(jsonpath, resp)


class QueryMeta(type):
    """
    metaclass to have consistent action/filter registry for new resources.
    """
    def __new__(cls, name, parents, attrs):
        if 'filter_registry' not in attrs:
            attrs['filter_registry'] = FilterRegistry(f"{name.lower()}.filters")
        if 'action_registry' not in attrs:
            attrs['action_registry'] = ActionRegistry(f"{name.lower()}%s.actions")
        return super(QueryMeta, cls).__new__(cls, name, parents, attrs)


class QueryResourceManager(ResourceManager, metaclass=QueryMeta):
    """QueryResourceManager"""
    class resource_type(ResourceTypeInfo):
        pass

    def __init__(self, data, options):
        super().__init__(data, options)
        self.source: DescribeSource = self.get_source(self.source_type)

    @property
    def source_type(self):
        return self.data.get("source", "describe-tencentcloud")

    def get_source(self, source_type):
        return sources.get(source_type)(self)

    def get_permissions(self):
        return self.source.get_permissions()

    def get_resource_query_params(self):
        return {}

    def resources(self):
        params = self.get_resource_query_params()
        resources = self.source.resources(params)
        return self.filter_resources(resources)

    def augment(self, resources):
        return resources


@sources.register("describe-tencentcloud")
class DescribeSource:
    """"""
    def __init__(self, resource_manager: QueryResourceManager) -> None:
        self.resource_manager = resource_manager
        self.query = ResourceQuery(resource_manager.session_factory)

    def resources(self, params=None):
        if params is None:
            params = {}
        return self.query.filter(self.resource_manager, params)

    def get_permissions(self):
        return None

    def augment(self, resources):
        return resources
