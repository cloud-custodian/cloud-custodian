# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources
from c7n.utils import local_session

log = logging.getLogger('custodian.openstack.query')


class ResourceQuery:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def filter(self, resource_manager, **params):
        m = resource_manager.resource_type
        session = local_session(self.session_factory)
        client = session.client()

        enum_op, extra_args = m.enum_spec
        if extra_args:
            params.update(extra_args)
        return self._invoke_client_enum(client, enum_op, params)

    def _invoke_client_enum(self, client, enum_op, params):
        if isinstance(enum_op, list):
            obj = client
            res = []
            for op in enum_op:
                obj = getattr(obj, op)
            for r in obj(**params):
                res.append(r.toDict() if not isinstance(enum_op, dict) else r)
        else:
            res = getattr(client, enum_op)(**params)
        return res


@sources.register('describe-openstack')
class DescribeSource:
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
    """metaclass to have consistent action/filter registry for new resources"""
    def __new__(cls, name, parents, attrs):
        if 'filter_registry' not in attrs:
            attrs['filter_registry'] = FilterRegistry(
                '%s.filters' % name.lower())
        if 'action_registry' not in attrs:
            attrs['action_registry'] = ActionRegistry(
                '%s.actions' % name.lower())

        return super(QueryMeta, cls).__new__(cls, name, parents, attrs)


class QueryResourceManager(ResourceManager, metaclass=QueryMeta):

    source_mapping = sources

    def __init__(self, ctx, data):
        super(QueryResourceManager, self).__init__(ctx, data)
        self.source = self.get_source(self.source_type)

    def get_permissions(self):
        return ()

    def get_source(self, source_type):
        if source_type in self.source_mapping:
            return self.source_mapping.get(source_type)(self)
        if source_type in sources:
            return sources.get(source_type)(self)
        raise KeyError("Invalid Source %s" % source_type)

    def get_client(self):
        client = local_session(self.session_factory).client()
        return client

    def get_model(self):
        return self.resource_type

    def get_cache_key(self, query):
        return {
            'resource': str(self.__class__.__name__),
            'source_type': self.source_type,
            'query': query,
        }

    @property
    def source_type(self):
        return self.data.get('source', 'describe-openstack')

    def get_resource_query(self):
        if 'query' in self.data:
            return {'filter': self.data.get('query')}

    def resources(self, query=None):
        q = query or self.get_resource_query()
        key = self.get_cache_key(q)
        resources = self.augment(self.source.get_resources(q))
        self._cache.save(key, resources)
        return self.filter_resources(resources)

    def augment(self, resources):
        return self.source.augment(resources)


class TypeMeta(type):
    def __repr__(cls):
        return "<TypeInfo group:%s version:%s>" % (
            cls.group,
            cls.version)


class TypeInfo(metaclass=TypeMeta):
    enum_spec = ()
