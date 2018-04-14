# Copyright 2018 Capital One Services, LLC
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

import six

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources
from c7n.utils import local_session


class ResourceQuery(object):

    def __init__(self, session_factory):
        self.session_factory = session_factory

    def filter(self, resource_manager, **params):
        m = resource_manager.resource_type
        client = local_session(self.session_factory).client(
            "%s.%s" % (m.service, m.client))
        enum_op, list_op = m.enum_spec
        op = getattr(getattr(client, enum_op), list_op)
        data = [self.to_dictionary(e) for e in op()]
        return data

    def to_dictionary(self, obj):
        if isinstance(obj, dict):
            data = {}
            for (k, v) in obj.items():
                data[k] = self.to_dictionary(v)
            return data
        elif hasattr(obj, "_ast"):
            return self.to_dictionary(obj._ast())
        elif hasattr(obj, "__iter__") and not isinstance(obj, str):
            return [self.to_dictionary(v) for v in obj]
        elif hasattr(obj, "__dict__"):
            data = dict([(key, self.to_dictionary(value))
                for key, value in obj.__dict__.iteritems()
                if not callable(value) and not key.startswith('_')])
            return data
        else:
            return obj


@sources.register('describe-azure')
class DescribeSource(object):

    def __init__(self, manager):
        self.manager = manager
        self.query = ResourceQuery(manager.session_factory)

    def get_resources(self, query):
        return self.query.filter(self.manager)

    def get_permissions(self):
        return ()

    def augment(self, resources):
        return resources


class QueryMeta(type):
    """metaclass to have consistent action/filter registry for new resources."""
    def __new__(cls, name, parents, attrs):
        if 'filter_registry' not in attrs:
            attrs['filter_registry'] = FilterRegistry(
                '%s.filters' % name.lower())
        if 'action_registry' not in attrs:
            attrs['action_registry'] = ActionRegistry(
                '%s.actions' % name.lower())

        return super(QueryMeta, cls).__new__(cls, name, parents, attrs)


@six.add_metaclass(QueryMeta)
class QueryResourceManager(ResourceManager):

    def __init__(self, data, options):
        super(QueryResourceManager, self).__init__(data, options)
        self.source = self.get_source(self.source_type)

    def get_permissions(self):
        return ()

    def get_source(self, source_type):
        return sources.get(source_type)(self)

    def get_cache_key(self, query):
        return {'source_type': self.source_type, 'query': query}

    @property
    def source_type(self):
        return self.data.get('source', 'describe-azure')

    def resources(self, query=None):
        key = self.get_cache_key(query)
        resources = self.augment(self.source.get_resources(query))
        self._cache.save(key, resources)
        return self.filter_resources(resources)

    def augment(self, resources):
        return resources