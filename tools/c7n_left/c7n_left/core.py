# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import fnmatch
import logging

from c7n.actions import ActionRegistry
from c7n.cache import NullCache
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager

from c7n.provider import Provider, clouds
from c7n.policy import PolicyExecutionMode


log = logging.getLogger("c7n.iac")


class IACSourceProvider(Provider):

    display_name = "IAC"

    def get_session_factory(self, options):
        return lambda *args, **kw: None

    def initialize(self, options):
        pass

    def initialize_policies(self, policies, options):
        return policies


class CollectionRunner:
    def __init__(self, policies, options, reporter):
        self.policies = policies
        self.options = options
        self.reporter = reporter

    def run(self):
        event = self.get_event()
        provider = self.get_provider()

        if not provider.match_dir(self.options.source_dir):
            raise NotImplementedError(
                "no %s source files found" % provider.provider_name
            )

        graph = provider.parse(self.options.source_dir)

        for p in self.policies:
            p.expand_variables(p.get_variables())
            p.validate()

        self.reporter.on_execution_started(self.policies)
        # consider inverting this order to allow for results grouped by policy
        # at the moment, we're doing results grouped by resource.
        for rtype, resources in graph.get_resources_by_type():
            for p in self.policies:
                if not self.match_type(rtype, p):
                    continue
                result_set = self.run_policy(p, graph, resources, event)
                if result_set:
                    self.reporter.on_results(result_set)
        self.reporter.on_execution_ended()

    def run_policy(self, policy, graph, resources, event):
        event = dict(event)
        event.update({"graph": graph, "resources": resources})
        return policy.push(event)

    def get_provider(self):
        provider_name = {p.provider_name for p in self.policies}.pop()
        provider = clouds[provider_name]()
        return provider

    def get_event(self):
        return {"config": self.options}

    @staticmethod
    def match_type(rtype, p):
        if isinstance(p.resource_type, str):
            return fnmatch.fnmatch(rtype, p.resource_type.split(".", 1)[-1])
        if isinstance(p.resource_type, list):
            for pr in p.resource_type:
                return fnmatch.fnmatch(rtype, pr.split(".", 1)[-1])


class IACSourceMode(PolicyExecutionMode):
    @property
    def manager(self):
        return self.policy.resource_manager

    def run(self, event, ctx):
        if not self.policy.is_runnable(event):
            return []

        resources = event["resources"]
        resources = self.manager.filter_resources(resources, event)
        return self.as_results(resources)

    def as_results(self, resources):
        return ResultSet([PolicyResourceResult(r, self.policy) for r in resources])


class ResultSet(list):
    pass


class PolicyResourceResult:
    def __init__(self, resource, policy):
        self.resource = resource
        self.policy = policy


class IACResourceManager(ResourceManager):

    filter_registry = FilterRegistry("iac.filters")
    action_registry = ActionRegistry("iac.actions")
    log = log

    def __init__(self, ctx, data):
        self.ctx = ctx
        self.data = data
        self._cache = NullCache(None)
        self.session_factory = lambda: None
        self.filters = self.filter_registry.parse(self.data.get("filters", []), self)
        self.actions = self.action_registry.parse(self.data.get("actions", []), self)

    def get_resource_manager(self, resource_type, data=None):
        return self.__class__(self.ctx, data or {})


class IACResourceMap(object):

    resource_class = None

    def __init__(self, prefix):
        self.prefix = prefix

    def __contains__(self, k):
        if k.startswith(self.prefix):
            return True
        return False

    def __getitem__(self, k):
        if k.startswith(self.prefix):
            return self.resource_class
        raise KeyError(k)

    def __iter__(self):
        return iter(())

    def notify(self, *args):
        pass

    def keys(self):
        return ()

    def items(self):
        return ()

    def get(self, k, default=None):
        # that the resource is in the map has alerady been verified
        # we get the unprefixed resource on get
        return self.resource_class


class ResourceGraph:
    def __init__(self, resource_data, src_dir):
        self.resource_data = resource_data
        self.src_dir = src_dir

    def get_resource_by_type(self):
        raise NotImplementedError()
