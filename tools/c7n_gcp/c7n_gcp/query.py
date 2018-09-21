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

import jmespath
import json
import logging
import six

from googleapiclient.errors import HttpError

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources
from c7n.utils import local_session


log = logging.getLogger('c7n_gcp.query')


class ResourceQuery(object):

    def __init__(self, session_factory):
        self.session_factory = session_factory

    def filter(self, resource_manager, **params):
        m = resource_manager.resource_type
        session = local_session(self.session_factory)
        client = session.client(
            m.service, m.version, m.component)

        # depends on resource scope
        if m.scope in ('project', 'zone'):
            project = session.get_default_project()
            if m.scope_template:
                project = m.scope_template.format(project)
            if m.scope_key:
                params[m.scope_key] = project
            else:
                params['project'] = project

        if m.scope == 'zone':
            if session.get_default_zone():
                params['zone'] = session.get_default_zone()

        enum_op, path, extra_args = m.enum_spec
        if extra_args:
            params.update(extra_args)
        return self._invoke_client_enum(
            client, enum_op, params, path)

    def _invoke_client_enum(self, client, enum_op, params, path):
        if client.supports_pagination(enum_op):
            results = []
            for page in client.execute_paged_query(enum_op, params):
                page_items = jmespath.search(path, page)
                if page_items:
                    results.extend(page_items)
            return results
        else:
            return jmespath.search(path,
                client.execute_query(enum_op, verb_arguments=params))


@sources.register('describe-gcp')
class DescribeSource(object):

    def __init__(self, manager):
        self.manager = manager
        self.query = ResourceQuery(manager.session_factory)

    def get_resources(self, query):
        if query is None:
            query = {}
        return self.query.filter(self.manager, **query)

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

    def get_client(self):
        return local_session(self.session_factory).client(
            self.resource_type.service,
            self.resource_type.version,
            self.resource_type.component)

    def get_model(self):
        return self.resource_type

    def get_cache_key(self, query):
        return {'source_type': self.source_type, 'query': query,
                'service': self.resource_type.service,
                'version': self.resource_type.version,
                'component': self.resource_type.component}

    def get_resource(self, resource_info):
        return self.resource_type.get(self.get_client(), resource_info)

    @property
    def source_type(self):
        return self.data.get('source', 'describe-gcp')

    def get_resource_query(self):
        if 'query' in self.data:
            return {'filter': self.data.get('query')}

    def resources(self, query=None):
        q = query or self.get_resource_query()
        key = self.get_cache_key(q)
        try:
            resources = self.augment(self.source.get_resources(q)) or []
        except HttpError as e:
            error = extract_error(e)
            if error is None:
                raise
            elif error == 'accessNotConfigured':
                log.warning(
                    "Resource:%s not available -> Service:%s not enabled on %s",
                    self.type,
                    self.resource_type.service,
                    local_session(self.session_factory).get_default_project())
                return []
            raise
        self._cache.save(key, resources)
        return self.filter_resources(resources)

    def augment(self, resources):
        return resources


class TypeMeta(type):

    def __repr__(cls):
        return "<TypeInfo service:%s component:%s scope:%s version:%s>" % (
            cls.service,
            cls.component,
            cls.scope,
            cls.version)


@six.add_metaclass(TypeMeta)
class TypeInfo(object):

    # api client construction information
    service = None
    version = None
    component = None

    # resource enumeration parameters

    scope = 'project'
    enum_spec = ('list', 'items[]', None)
    # ie. when project is passed instead as parent
    scope_key = None
    # custom formatting for scope key
    scope_template = None

    # individual resource retrieval method, for serverless policies.
    get = None


ERROR_REASON = jmespath.compile('error.errors[0].reason')


def extract_error(e):

    try:
        edata = json.loads(e.content)
    except Exception:
        return None
    return ERROR_REASON.search(edata)
