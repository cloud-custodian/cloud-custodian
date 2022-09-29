import fnmatch
import logging

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.cache import NullCache
from c7n.provider import Provider, clouds
from c7n.policy import PolicyExecutionMode

from tfparse import load_from_path


log = logging.getLogger("c7n.iaac")


class IAACSourceProvider(Provider):

    display_name = "IAAC"

    def get_session_factory(self, options):
        return lambda *args, **kw: None

    def initialize(self):
        pass

    def initialize_policies(self, policies):
        pass


class IAACSourceMode(PolicyExecutionMode):
    def run(self, event=None):
        event = self.resolve_event(event)

        if not self.policy.is_runnable(event):
            pass

        source_format = self.get_source_format(event["source_dir"])
        if not source_format:
            log.warning("iaac definition format not detected")

        self.manager.source_format = source_format
        self.manager.graph = graph = source_format.parse(
            self.manager.ctxt.options["source_dir"]
        )
        resources = graph.get_resources_by_type(self.get_resource_types(graph))

        rcount = len(resources)
        log.debug("loaded %d resources", rcount)
        resources = self.manager.filter_resources(resources, event)
        results = source_format.as_results(resources)

        return results

    def resolve_event(self, event):
        event = dict(self.manager.ctx.options)
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

    def get_source_format(self, source_dir):
        if self.manager.ctx.options.format == "terraform":
            return TerraformSource(self.manager)
        raise NotImplementedError()


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


class IAACResource:

    filter_registry = FilterRegistry("iaac.filters")
    action_registry = ActionRegistry("iaac.actions")

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


class TerraformResource(IAACResource):
    pass


class TerraformResourceMap(IAACResourceMap):

    resource_class = TerraformResource


@clouds.register("terraform")
class TerraformProvider(IAACSourceProvider):

    resource_prefix = "terraform"
    resource_map = TerraformResourceMap(resource_prefix)
    resources = resource_map


class TerraformSource(IAACSourceMode):
    @staticmethod
    def match_dir(self, source_dir):
        files = source_dir.glob("*.tf")
        files += source_dir.glob("*.tf.json")
        return files

    def parse(self, source_dir):
        return TerraformGraph(load_from_path(source_dir))


class ResourceGraph:
    def __init__(self, resource_data):
        self.resource_data = resource_data

    def get_resource_types(self):
        raise NotImplementedError()


class TerraformGraph(ResourceGraph):
    def get_resoruce_types(self):
        pass
