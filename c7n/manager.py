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
from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from c7n import cache
from c7n.executor import ThreadPoolExecutor
from c7n.registry import PluginRegistry
from c7n.utils import dumps


resources = PluginRegistry('resources')


class ResourceManager(object):

    filter_registry = None
    action_registry = None
    executor_factory = ThreadPoolExecutor
    retry = None

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

    def match_ids(self, ids):
        """return ids that match this resource type's id format."""
        return ids

    @classmethod
    def get_permissions(cls):
        return ()

    def get_resources(self, resource_ids):
        """Retrieve a set of resources by id."""
        return []

    def resources(self):
        raise NotImplementedError("")

    def get_resource_manager(self, resource_type, data=None):
        klass = resources.get(resource_type)
        if klass is None:
            raise ValueError(resource_type)
        # if we're already querying via config carry it forward
        if not data and self.source_type == 'config' and getattr(
                klass.get_model(), 'config_type', None):
            return klass(self.ctx, {'source': self.config_type})
        return klass(self.ctx, data or {})

    def filter_resources(self, resources, event=None):
        original = len(resources)
        if event and event.get('debug', False):
            self.log.info(
                "Filtering resources with %s", self.filters)
        for f in self.filters:
            if not resources:
                break
            rcount = len(resources)
            resources = f.process(resources, event)
            if event and event.get('debug', False):
                self.log.debug(
                    "applied filter %s %d->%d", f, rcount, len(resources))
        self.log.debug("Filtered from %d to %d %s" % (
            original, len(resources), self.__class__.__name__.lower()))
        return resources

    def get_model(self):
        """Returns the resource meta-model.
        """
        return self.query.resolve(self.resource_type)
