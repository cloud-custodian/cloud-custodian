import fnmatch
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
    def __init__(self, policies, options):
        self.policies = policies
        self.options = options

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

        for rtype, resources in graph.get_resources_by_type():
            for p in self.policies:
                if rtype != p.resource_type.split(".", 1)[-1]:
                    continue
                yield self.run_policy(p, graph, resources, event)

    def run_policy(self, policy, graph, resources, event):
        event = dict(event)
        event.update({"graph": graph, "resources": resources})
        return policy.push(event)

    def get_provider(self):
        provider_name = {p.provider_name for p in self.policies}.pop()
        provider = clouds[provider_name]()
        return provider

    def get_event(self):
        return {}

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
            pass

        resources = event["resources"]
        log.debug("loaded %d resources", len(resources))
        resources = self.manager.filter_resources(resources, event)
        return self.as_results(resources)

    def resolve_event(self, event):
        event = dict(self.policy.options)
        return event

    def as_results(self, resources):
        return ResultSet(map(PolicyResourceResult, resources))

    def get_resource_types(self, graph):
        resource_type = self.manager.policy.resource_type
        if isinstance(resource_type, list):
            rtypes = resource_type
        else:
            rtypes = (resource_type,)
        for r in rtypes:
            rtypes += fnmatch.filter(graph.get_resource_types())
        return sorted(set(rtypes))


class ResultSet(list):
    pass


class PolicyResourceResult(dict):
    def source_file(self):
        pass

    def source_lines(self):
        pass

    def start_position(self):
        pass

    def end_posiition(self):
        pass


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

    @classmethod
    def get_permissions(cls):
        return ()

    def get_resources(self, resource_ids):
        return []

    def resources(self):
        return []

    def validate(self):
        pass

    def get_deprecations(self):
        return []

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

    resource_prefix = "terraform"
    resource_map = TerraformResourceMap(resource_prefix)
    resources = resource_map

    def initialize_policies(self, policies, options):
        for p in policies:
            p.data["mode"] = {"type": "terraform-source"}
        return policies

    def parse(self, source_dir):
        graph = TerraformGraph(load_from_path(source_dir))
        log.debug("Loaded %d resources", len(graph))
        return graph

    def match_dir(self, source_dir):
        files = list(source_dir.glob("*.tf"))
        files += list(source_dir.glob("*.tf.json"))
        return files


@execution.register("terraform-source")
class TerraformSource(IAACSourceMode):

    schema = type_schema("terraform-source")


class TerraformResource:
    def __init__(self, name, data):
        self.name = name
        self.location = data["__tfmeta"]
        self.data = data


class ResourceGraph:
    def __init__(self, resource_data):
        self.resource_data = resource_data

    def get_resource_by_type(self):
        raise NotImplementedError()


class TerraformGraph(ResourceGraph):
    def __len__(self):
        return sum(map(len, self.resource_data.values()))

    def get_resources_by_type(self):
        for type_name, type_items in self.resource_data.items():
            yield type_name, [
                TerraformResource(name, data) for name, data in type_items.items()
            ]
