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

import logging
import six
from c7n_azure.actions.notify import Notify
from c7n_azure.actions.logic_app import LogicAppAction
from c7n_azure import constants
from c7n_azure.provider import resources

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources
from c7n.utils import local_session


log = logging.getLogger('custodian.azure.query')


class ResourceQuery(object):

    def __init__(self, session_factory):
        self.session_factory = session_factory

    def filter(self, resource_manager, **params):
        m = resource_manager.resource_type
        enum_op, list_op, extra_args = m.enum_spec

        if extra_args:
            params.update(extra_args)

        op = getattr(getattr(resource_manager.get_client(), enum_op), list_op)
        data = [r.serialize(True) for r in op(**params)]

        return data

    @staticmethod
    def resolve(resource_type):
        if not isinstance(resource_type, type):
            raise ValueError(resource_type)
        else:
            m = resource_type
        return m


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


class ChildResourceQuery(ResourceQuery):
    """A resource query for resources that must be queried with parent information.
    Several resource types can only be queried in the context of their
    parents identifiers. ie. SQL and Cosmos databases
    """

    def __init__(self, session_factory, manager):
        super(ChildResourceQuery, self).__init__(session_factory)
        self.manager = manager

    def filter(self, resource_manager, **params):
        """Query a set of resources."""
        m = self.resolve(resource_manager.resource_type)
        client = resource_manager.get_client()

        enum_op, list_op, extra_args = m.enum_spec

        parents = self.manager.get_resource_manager(m.parent_manager_name)

        # Have to query separately for each parent's children.
        results = []
        for parent in parents.resources():
            # There are 2 types of extra_args:
            #   - static values stored in 'extra_args' dict (e.g. some type)
            #   - dynamic values are retrieved via 'extra_args' method (e.g. parent name)
            if extra_args:
                params.update({key: extra_args[key](parent) for key in extra_args.keys()})

            params.update(m.extra_args(parent))

            # Some resources might not have enum_op piece (non-arm resources)
            if enum_op:
                op = getattr(getattr(client, enum_op), list_op)
            else:
                op = getattr(client, list_op)

            try:
                subset = [r.serialize(True) for r in op(**params)]

                # If required, append parent resource ID to all child resources
                if m.annotate_parent:
                    for r in subset:
                        r[m.parent_key] = parent[parents.resource_type.id]

                if subset:
                    results.extend(subset)
            except Exception as e:
                log.warning('{0}.{1} failed for {2}. {3}'.format(m.client,
                                                                 list_op,
                                                                 parent[parents.resource_type.id],
                                                                 e))
                if m.raise_on_exception:
                    raise e

        return results


@sources.register('describe-child-azure')
class ChildDescribeSource(DescribeSource):

    resource_query_factory = ChildResourceQuery

    def __init__(self, manager):
        self.manager = manager
        self.query = self.get_query()

    def get_query(self):
        return self.resource_query_factory(
            self.manager.session_factory, self.manager)


class TypeMeta(type):

    def __repr__(cls):
        return "<Type info service:%s client: %s>" % (
            cls.service,
            cls.client)


@six.add_metaclass(TypeMeta)
class TypeInfo(object):
    # api client construction information
    service = ''
    client = ''

    resource = constants.RESOURCE_ACTIVE_DIRECTORY


@six.add_metaclass(TypeMeta)
class ChildTypeInfo(TypeInfo):
    # api client construction information for child resources
    parent_manager_name = ''
    annotate_parent = True
    raise_on_exception = True
    parent_key = 'c7n:parent-id'

    @classmethod
    def extra_args(cls, parent_resource):
        return {}


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
        self._session = None

    def augment(self, resources):
        return resources

    def get_permissions(self):
        return ()

    def get_source(self, source_type):
        return sources.get(source_type)(self)

    def get_session(self):
        if self._session is None:
            self._session = local_session(self.session_factory)
        return self._session

    def get_client(self, service=None):
        if not service:
            return self.get_session().client(
                "%s.%s" % (self.resource_type.service, self.resource_type.client))
        return self.get_session().client(service)

    def get_cache_key(self, query):
        return {'source_type': self.source_type, 'query': query}

    @classmethod
    def get_model(cls):
        return ResourceQuery.resolve(cls.resource_type)

    @property
    def source_type(self):
        return self.data.get('source', 'describe-azure')

    def resources(self, query=None):
        key = self.get_cache_key(query)
        resources = self.augment(self.source.get_resources(query))
        self._cache.save(key, resources)
        return self.filter_resources(resources)

    def get_resources(self, resource_ids, **params):
        resource_client = self.get_client()
        m = self.resource_type
        get_client, get_op, extra_args = m.get_spec

        if extra_args:
            params.update(extra_args)

        op = getattr(getattr(resource_client, get_client), get_op)
        data = [
            op(rid, **params)
            for rid in resource_ids
        ]
        return [r.serialize(True) for r in data]

    @staticmethod
    def register_actions_and_filters(registry, _):
        for resource in registry.keys():
            klass = registry.get(resource)
            klass.action_registry.register('notify', Notify)
            klass.action_registry.register('logic-app', LogicAppAction)


@six.add_metaclass(QueryMeta)
class ChildResourceManager(QueryResourceManager):

    child_source = 'describe-child-azure'

    @property
    def source_type(self):
        source = self.data.get('source', self.child_source)
        if source == 'describe':
            source = self.child_source
        return source

    def get_parent_manager(self):
        return self.get_resource_manager(self.resource_type.parent_manager_name)

    def get_session(self):
        if self._session is None:
            session = super(ChildResourceManager, self).get_session()
            if self.resource_type.resource != constants.RESOURCE_ACTIVE_DIRECTORY:
                session = session.get_session_for_resource(self.resource_type.resource)
            self._session = session

        return self._session


resources.subscribe(resources.EVENT_FINAL, QueryResourceManager.register_actions_and_filters)
