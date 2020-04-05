# Copyright 2020 Kapil Thangavelu
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import fnmatch
import os

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
        return


class DiskSource:
    def __init__(self, queries):
        self.queries = queries

    def validate(self):
        for q in self.queries:
            if not os.path.exists(q["path"]):
                raise PolicyValidationError("invalid disk path %s" % q)

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
        for root, files, dirs in os.path.walk(path):
            if glob:
                files = fnmatch.filter(files, glob)
            for f in files:
                data = self.load_file(os.path.join(root, f), resource_key)
                yield data

    def load_file(self, path, resource_key):
        data = load_file(path)
        if resource_key:
            records = jmespath.search(resource_key, data)
        elif not isinstance(data, list):
            raise PolicyExecutionError(
                "found disk records at %s in format %s without a resource_expr"
                % (self.path, type(records))
            )
        else:
            records = data
        return DataFile(path, resource_key, records)


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
            raise PolicyValidationError("invalid source %s")
        self.get_source().validate()

    def get_resources(self, resource_ids):
        return []

    def resources(self):
        source = self.get_source()
        resources = list(source)
        return resources

    def get_source(self):
        source_type = self.data.get("source", "disk")
        return self.source_mapping[source_type](self.data.get("query", []))
