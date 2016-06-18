"""
Query capability built on skew metamodel


tags_spec -> s3, elb, rds

detail_spec
   - aws.route53.healthcheck -> health check info
   - aws.cloudformation.stack -> stack resources
   - aws.dymanodb.table ->
"""
import jmespath

from botocore.client import ClientError
from skew.resources import find_resource_class

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.utils import local_session
from c7n.manager import ResourceManager


class QueryMeta(type):

    def __new__(cls, name, parents, attrs):
        if 'filter_registry' not in attrs:
            attrs['filter_registry'] = FilterRegistry(
                '%s.filters' % name.lower())
        if 'action_registry' not in attrs:
            attrs['action_registry'] = ActionRegistry(
                '%s.filters' % name.lower())
        #if attrs['resource_type']:
        #    m = ResourceQuery.resolve(attrs['resource_type'])
        return super(QueryMeta, cls).__new__(cls, name, parents, attrs)


class QueryResourceManager(ResourceManager):

    __metaclass__ = QueryMeta

    resource_type = ""

    def __init__(self, data, options):
        super(QueryResourceManager, self).__init__(data, options)
        self.query = ResourceQuery(self.session_factory)

    def resources(self, query=None):
        key = {'region': self.config.region,
               'resource': str(self.resource_type),
               'q': query}

        if self._cache.load():
            resources = self._cache.get(key)
            if resources is not None:
                self.log.debug("Using cached %s: %d" % (
                    self.resource_type, len(resources)))

        if query is None:
            query = {}

        resources = self.query.filter(self.resource_type, **query)
        resources = self.augment(resources)
        self._cache.save(key, resources)
        return self.filter_resources(resources)

    def get_resources(self, ids):
        try:
            resources = self.query.get(self.resource_type, ids)
            resources = self.augment(resources)
            return resources
        except ClientError as e:
            self.log.warning("event ids not resolved: %s error:%s" % (ids, e))
            return []

    def augment(self, resources):
        """subclasses may want to augment resources with additional information.

        ie. we want tags by default (rds, elb), and policy, location, acl for
        s3 buckets.
        """
        return resources


class ResourceQuery(object):

    def __init__(self, session_factory):
        self.session_factory = session_factory

    @staticmethod
    def resolve(resource_type):
        if not isinstance(resource_type, type):
            m = find_resource_class(resource_type).Meta
        else:
            m = resource_type
        return m

    def filter(self, resource_type, **params):
        """Query a set of resources."""
        m = self.resolve(resource_type)
        client = local_session(self.session_factory).client(
            m.service)
        enum_op, path, extra_args = m.enum_spec
        if extra_args:
            params.update(extra_args)

        if client.can_paginate(enum_op):
            p = client.get_paginator(enum_op)
            results = p.paginate(**params)
            data = results.build_full_result()
        else:
            op = getattr(client, enum_op)
            data = op(**params)
        if path:
            path = jmespath.compile(path)
            data = path.search(data)
        return data

    def get(self, resource_type, identity):
        """Get resources by identities
        """
        m = self.resolve(resource_type)
        params = {}
        client_filter = False

        # Try to formulate server side query
        if m.filter_name:
            if m.filter_type == 'list':
                params[m.filter_name] = identity
            elif m.filter_type == 'scalar':
                assert len(identity) == 1, "Scalar server side filter"
                params[m.filter_name] = identity[0]
        else:
            client_filter = True

        session = local_session(self.session_factory)
        client = session.client(m.service)

        resources = self.filter(resource_type, **params)
        if client_filter:
            resources = [r for r in resources if r[m.id] in identity]

        return resources

