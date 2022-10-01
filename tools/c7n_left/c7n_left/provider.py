# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import logging

from c7n.actions import ActionRegistry
from c7n.cache import NullCache
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.policy import execution

from c7n.provider import Provider, clouds
from c7n.policy import PolicyExecutionMode
from c7n.utils import type_schema

from tfparse import load_from_path


log = logging.getLogger("c7n.iaac")


class IAACSourceProvider(Provider):

    display_name = "IAAC"

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
                if rtype != p.resource_type.split(".", 1)[-1]:
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
    def match_type(rtype, policies):
        for p in policies:
            if p.resource_type == rtype:
                return True


class IAACSourceMode(PolicyExecutionMode):
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


class IAACResourceManager(ResourceManager):

    filter_registry = FilterRegistry("iaac.filters")
    action_registry = ActionRegistry("iaac.actions")
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


class IAACResourceMap(object):

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

    def notify(self, *args):
        pass

    def items(self):
        return ()

    def get(self, k, default=None):
        return self.resource_class
        try:
            return self[k]
        except KeyError:
            return default


class TerraformResourceManager(IAACResourceManager):
    pass


class TerraformResourceMap(IAACResourceMap):

    resource_class = TerraformResourceManager


@clouds.register("terraform")
class TerraformProvider(IAACSourceProvider):

    display_name = "Terraform"
    resource_prefix = "terraform"
    resource_map = TerraformResourceMap(resource_prefix)
    resources = resource_map

    def initialize_policies(self, policies, options):
        for p in policies:
            p.data["mode"] = {"type": "terraform-source"}
        return policies

    def parse(self, source_dir):
        graph = TerraformGraph(load_from_path(source_dir), source_dir)
        log.debug("Loaded %d resources", len(graph))
        return graph

    def match_dir(self, source_dir):
        files = list(source_dir.glob("*.tf"))
        files += list(source_dir.glob("*.tf.json"))
        return files


@execution.register("terraform-source")
class TerraformSource(IAACSourceMode):

    schema = type_schema("terraform-source")


class TerraformResource(dict):

    __slots__ = ("name", "data", "location")

    # pygments lexer
    format = "terraform"

    def __init__(self, name, data):
        self.name = name
        self.location = data["__tfmeta"]
        super().__init__(data)

    @property
    def filename(self):
        return self.location["filename"]

    @property
    def line_start(self):
        return self.location["line_start"]

    @property
    def line_end(self):
        return self.location["line_end"]

    @property
    def src_dir(self):
        return self.location["src_dir"]

    def get_source_lines(self):
        lines = (self.src_dir / self.filename).read_text().split("\n")
        return lines[self.line_start - 1 : self.line_end]  # noqa


class ResourceGraph:
    def __init__(self, resource_data, src_dir):
        self.resource_data = resource_data
        self.src_dir = src_dir

    def get_resource_by_type(self):
        raise NotImplementedError()


class TerraformGraph(ResourceGraph):
    def __len__(self):
        return sum(map(len, self.resource_data.values()))

    def get_resources_by_type(self, types=()):
        if isinstance(types, str):
            types = (types,)

        for type_name, type_items in self.resource_data.items():
            if types and type_name not in types:
                continue
            resources = []
            for name, data in type_items.items():
                data["__tfmeta"]["src_dir"] = self.src_dir
                resources.append(TerraformResource(name, data))
            yield type_name, resources
