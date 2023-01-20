# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
from collections import defaultdict
import fnmatch
import logging

from c7n.actions import ActionRegistry
from c7n.cache import NullCache
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager

from c7n.provider import Provider, clouds
from c7n.policy import PolicyExecutionMode

from .filters import Traverse
from .utils import SEVERITY_LEVELS

log = logging.getLogger("c7n.iac")


class IACSourceProvider(Provider):

    display_name = "IAC"

    def get_session_factory(self, options):
        return lambda *args, **kw: None

    def initialize(self, options):
        pass

    def initialize_policies(self, policies, options):
        return policies


class ExecutionFilter:

    supported_filters = ("policy", "type", "severity")

    def __init__(self, filters):
        self.filters = filters

    @classmethod
    def parse(cls, options):
        """cli option filtering support

        --filters "type=aws_sqs_queue,aws_rds_* policy=*encryption* severity=high"
        """
        if not options.filters:
            return cls(defaultdict(list))

        filters = {}
        for kv in options.filters.split(" "):
            if "=" not in kv:
                raise ValueError("key=value pair missing `=`")
            k, v = kv.split("=")
            if k not in cls.supported_filters:
                raise ValueError("unsupported filter %s" % k)
            if "," in v:
                v = v.split(",")
            else:
                v = [v]
            filters[k] = v

        invalid_severities = set()
        if filters["severity"]:
            invalid_severities = set(filters["severity"]).difference(SEVERITY_LEVELS)
        if invalid_severities:
            raise ValueError(
                "invalid severity for filtering %s" % (", ".join(invalid_severities))
            )

    def _filter_policy_name(self, policies):
        if not self.filters["policy"]:
            return policies
        results = []
        for pf in self.filters["policy"]:
            for p in policies:
                if fnmatch.fnmatch(p.name, pf):
                    results.append(p)
        return results

    def _filter_policy_severity(self, policies):
        # if we have a single severity filter we default to filtering
        # all severities at a higher level. ie filtering on medium,
        # gets and critcial, high.
        if not self.filters["severity"]:
            return policies

        def get_severity(p):
            return p.data.get("metadata", {}).get("severity")

        def filter_severity(p):
            severity = get_severity(p)
            p_slevel = SEVERITY_LEVELS[severity]
            f_slevel = SEVERITY_LEVELS[self.filters["severity"][0]]
            return p_slevel <= f_slevel

        if len(self.filters["severity"]) == 1:
            return list(filter(filter_severity, policies))

        results = []
        # if we mulitple, match on each level
        fseverities = set(self.filters["severity"])
        for p in policies:
            if get_severity(sf) not in fseverities:
                continue
            results.append(p)
        return results

    def filter_policies(self, policies):
        policies = self._filter_policy_name(policies)
        policies = self._filter_policy_level(policies)
        return policies

    def filter_resources(self, rtype, resources):
        if not self.filters["type"]:
            return resources
        for rf in self.filters["type"]:
            if fnmatch.fnmatch(rtype, rf):
                return resources
        return []


class CollectionRunner:
    def __init__(self, policies, options, reporter):
        self.policies = policies
        self.options = options
        self.reporter = reporter

    def run(self) -> bool:
        # return value is used to signal process exit code.
        event = self.get_event()
        provider = self.get_provider()

        if not provider.match_dir(self.options.source_dir):
            log.warning("no %s source files found" % provider.type)
            return True

        graph = provider.parse(self.options.source_dir)

        for p in self.policies:
            p.expand_variables(p.get_variables())
            p.validate()

        self.reporter.on_execution_started(self.policies, graph)
        # consider inverting this order to allow for results grouped by policy
        # at the moment, we're doing results grouped by resource.
        found = False
        for rtype, resources in graph.get_resources_by_type():
            if self.options.exec_filter:
                resources = self.options.exec_filter.filter_resources(resources)
            if not resources:
                continue
            for p in self.policies:
                if not self.match_type(rtype, p):
                    continue
                result_set = self.run_policy(p, graph, resources, event)
                if result_set:
                    self.reporter.on_results(result_set)
                    found = True
        self.reporter.on_execution_ended()
        return found

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


IACResourceManager.filter_registry.register("traverse", Traverse)


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

    def __len__(self):
        raise NotImplementedError()

    def get_resource_by_type(self):
        raise NotImplementedError()

    def resolve_refs(self, resource, target_type):
        raise NotImplementedError()
