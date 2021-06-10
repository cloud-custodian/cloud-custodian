# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Data Resource Provider implementation.
"""
import os
from pathlib import Path

import jmespath

from c7n.actions import ActionRegistry
from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.provider import Provider, clouds
from c7n.registry import PluginRegistry
from c7n.utils import load_file


@clouds.register("c7n")
class CustodianProvider(Provider):

    display_name = "Custodian Core"
    resources = PluginRegistry("policy")
    resource_prefix = "c7n"
    # lazy load chicken sacrifice
    resource_map = {"c7n.data": "c7n.data.Data"}

    def get_session_factory(self, config):
        return NullSession()

    def initialize(self, options):
        return

    def initialize_policies(self, policy_collection, options):
        return policy_collection


class NullSession:
    """dummy session"""


class StaticSource:
    def __init__(self, queries):
        self.queries = queries

    def __iter__(self):
        records = []
        for q in self.queries:
            records.extend(q.get("records", ()))
        return iter(records)

    def validate(self):
        for q in self.queries:
            if not isinstance(q.get("records", None), (list, tuple)):
                raise PolicyValidationError("invalid static data source `records`")


class DiskSource:
    def __init__(self, queries):
        self.queries = queries

    def validate(self):
        for q in self.queries:
            if not os.path.exists(q["path"]):
                raise PolicyValidationError("invalid disk path %s" % q)
            if os.path.isdir(q["path"]) and "glob" not in q:
                raise PolicyValidationError("glob pattern required for dir")

    def __iter__(self):
        for q in self.queries:
            for collection in self.scan_path(
                path=q["path"], resource_key=q.get("key"), glob=q.get("glob")
            ):
                for p in collection:
                    yield p

    def scan_path(self, path, glob, resource_key):
        if os.path.isfile(path):
            yield self.load_file(path, resource_key)
            return

        for path in Path(path).glob(glob):
            yield self.load_file(str(path), resource_key)

    def load_file(self, path, resource_key):
        data = load_file(path)
        if resource_key:
            data = jmespath.search(resource_key, data)
        if not isinstance(data, list):
            raise PolicyExecutionError(
                "found disk records at %s in non list format %s" % (path, type(data))
            )
        return DataFile(path, resource_key, data)


class DataFile:

    __slots__ = ("path", "records", "resource_key")

    def __init__(self, path, resource_key, records):
        self.path = path
        self.resource_key = resource_key
        self.records = records

    def __iter__(self):
        return iter(self.records)


@CustodianProvider.resources.register("data")
class Data(ResourceManager):

    action_registry = ActionRegistry("c7n.data.actions")
    filter_registry = FilterRegistry("c7n.data.filters")
    source_mapping = {"static": StaticSource, "disk": DiskSource}

    def validate(self):
        if self.data.get("source", "disk") not in self.source_mapping:
            raise PolicyValidationError("invalid source %s" % self.data["source"])
        self.get_source().validate()

    def get_resources(self, resource_ids):
        return []

    def resources(self):
        with self.ctx.tracer.subsegment("resource-fetch"):
            source = self.get_source()
            resources = list(source)
        with self.ctx.tracer.subsegment("filter"):
            resources = self.filter_resources(resources)
        return resources

    def get_source(self):
        source_type = self.data.get("source", "disk")
        return self.source_mapping[source_type](self.data.get("query", []))
