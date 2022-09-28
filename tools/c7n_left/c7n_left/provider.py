import fnmatch
import logging

from c7n.provider import Provider, clouds
from c7n.policy import PolicyExecutionMode

from tfparse import load_from_path


log = logging.getLogger('c7n.iaac')


class IAACSourceProvider(Provider):

    display_name = "IAAC"


class IAACSourceMode(PolicyExecutionMode):
    def run(self, event=None):
        event = dict(self.manager.ctx.options)

        if not self.policy.is_runnable(event):
            pass

        source_format = self.get_source_format(event['source_dir'])
        if not source_format:
            log.warning("iaac definition format not detected")

        self.manager.source_format = source_format
        self.manager.graph = graph = source_format.parse(
            self.manager.ctxt.options["source_dir"]
        )
        resources = graph.get_resources_by_type(self.get_resource_types(graph))

        rcount = len(resources)
        log.debug('loaded %d resources', rcount)
        resources = self.manager.filter_resources(resources, event)
        results = source_format.as_results(resources)

        return results

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


@clouds.register('terraform')
class TerraformProvider(IAACSourceProvider):

    resource_prefix = "terraform"


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
