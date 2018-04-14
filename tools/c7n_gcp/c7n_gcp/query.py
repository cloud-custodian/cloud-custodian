# Copyright 2017-2018 Capital One Services, LLC
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
import os
import jmespath

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources
from c7n.utils import local_session


class ResourceQuery(object):

    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.default_region = get_default_region()
        self.default_project = get_default_project()
        self.default_zone = get_default_zone()

    def filter(self, resource_manager, **params):
        m = resource_manager.resource_type
        client = local_session(self.session_factory).client(
            m.service, m.version, m.component)

        # depends on resource scope
        if m.scope in ('project', 'zone') and self.default_project:
            params['project'] = self.default_project

        if m.scope == 'zone' and self.default_zone:
            params['zone'] = self.default_zone

        enum_op, path, extra_args = m.enum_spec
        if extra_args:
            params.update(extra_args)
        return self._invoke_client_enum(
            client, enum_op, params, path)

    def _invoke_client_enum(self, client, enum_op, params, path):
        if client.supports_pagination(enum_op):
            results = []
            for page in client.execute_paged_query(enum_op, params):
                results.extend(jmespath.search(path, page))
            return results
        else:
            return jmespath.search(path,
                client.execute_query(enum_op, verb_arguments=params))


# We use env vars per terraform gcp precedence order.
def get_default_region():
    for k in ('GOOGLE_REGION', 'GCLOUD_REGION', 'CLOUDSDK_COMPUTE_REGION'):
        if k in os.environ:
            return os.environ[k]


def get_default_project():
    for k in ('GOOGLE_PROJECT', 'GCLOUD_PROJECT', 'CLOUDSDK_CORE_PROJECT'):
        if k in os.environ:
            return os.environ[k]


def get_default_zone():
    for k in ('GOOGLE_ZONE', 'GCLOUD_ZONE', 'CLOUDSDK_COMPUTE_ZONE'):
        if k in os.environ:
            return os.environ[k]


@sources.register('describe-gcp')
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
        return self.data.get('source', 'describe-gcp')

    def resources(self, query=None):
        key = self.get_cache_key(query)
        resources = self.augment(self.source.get_resources(query))
        self._cache.save(key, resources)
        return self.filter_resources(resources)

    def augment(self, resources):
        return resources


class TypeInfo(object):

    service = None
    version = None
    scope = 'project'
    enum_spec = ('list', 'items', None)
