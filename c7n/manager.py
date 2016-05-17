# Copyright 2016 Capital One Services, LLC
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
import logging

from c7n import cache
from c7n.executor import ThreadPoolExecutor
from c7n.registry import PluginRegistry
from c7n.utils import dumps


resources = PluginRegistry('resources')


class ResourceManager(object):

    filter_registry = None
    action_registry = None

    supports_dry_run = False

    executor_factory = ThreadPoolExecutor

    def __init__(self, ctx, data):
        self.ctx = ctx
        self.session_factory = ctx.session_factory
        self.config = ctx.options
        self.data = data
        self.log_dir = ctx.log_dir
        self._cache = cache.factory(self.ctx.options)
        self.log = logging.getLogger('custodian.resources.%s' % (
            self.__class__.__name__.lower()))

        if self.filter_registry:
            self.filters = self.filter_registry.parse(
                self.data.get('filters', []), self)
        if self.action_registry:
            self.actions = self.action_registry.parse(
                self.data.get('actions', []), self)

    def format_json(self, resources, fh):
        return dumps(resources, fh, indent=2)

    def resource_query(self):
        """Return server side query filter for the given api."""
        return []

    def get_resources(self, resource_ids):
        return []

    def filter_resources(self, resources, event=None):
        original = len(resources)
        for f in self.filters:
            if event and event['debug']:
                self.log.info("applying filter %s", f)
            resources = f.process(resources, event)
            if not resources:
                break
        self.log.info("Filtered from %d to %d %s" % (
            original, len(resources), self.__class__.__name__.lower()))
        return resources
