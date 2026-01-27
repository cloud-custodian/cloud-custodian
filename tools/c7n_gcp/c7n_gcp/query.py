# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import itertools
import logging
import re
import jmespath

from googleapiclient.errors import HttpError

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources, MaxResourceLimit
from c7n.utils import local_session, chunks, jmespath_search, jmespath_compile


log = logging.getLogger('c7n_gcp.query')


class ResourceQuery:

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
                page_items = jmespath_search(path, page)
                if page_items:
                    results.extend(page_items)
            return results
        else:
            return jmespath_search(path,
                client.execute_query(enum_op, verb_arguments=params))


@sources.register('describe-gcp')
class DescribeSource:

    def __init__(self, manager):
        self.manager = manager
        self.query = ResourceQuery(manager.session_factory)

    def get_resources(self, query):
        if query is None:
            query = {}
        return self.query.filter(self.manager, **query)

    def get_permissions(self):
        m = self.manager.resource_type
        if m.permissions:
            return m.permissions
        method = m.enum_spec[0]
        if method == 'aggregatedList':
            method = 'list'
        component = m.component
        if '.' in component:
            component = component.split('.')[-1]
        return ("%s.%s.%s" % (
            m.perm_service or m.service, component, method),)

    def augment(self, resources):
        return resources


@sources.register('inventory')
class AssetInventory:

    permissions = ("cloudasset.assets.searchAllResources",
                   "cloudasset.assets.exportResource")

    def __init__(self, manager):
        self.manager = manager

    def get_resources(self, query):
        session = local_session(self.manager.session_factory)
        if query is None:
            query = {}
        if 'scope' not in query:
            query['scope'] = 'projects/%s' % session.get_default_project()
        if 'assetTypes' not in query:
            query['assetTypes'] = [self.manager.resource_type.asset_type]

        search_client = session.client('cloudasset', 'v1p1beta1', 'resources')
        resource_client = session.client('cloudasset', 'v1', 'v1')
        resources = []

        results = list(search_client.execute_paged_query('searchAll', query))
        for resource_set in chunks(itertools.chain(*[rs['results'] for rs in results]), 100):
            rquery = {
                'parent': query['scope'],
                'contentType': 'RESOURCE',
                'assetNames': [r['name'] for r in resource_set]}
            for history_result in resource_client.execute_query(
                    'batchGetAssetsHistory', rquery).get('assets', ()):
                resource = history_result['asset']['resource']['data']
                resource['c7n:history'] = {
                    'window': history_result['window'],
                    'ancestors': history_result['asset']['ancestors']}
                resources.append(resource)
        return resources

    def get_permissions(self):
        return self.permissions

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


class QueryResourceManager(ResourceManager, metaclass=QueryMeta):
    # The resource manager type is injected by the PluginRegistry.register
    # decorator.
    type: str
    resource_type: 'TypeInfo'

    def __init__(self, ctx, data):
        super(QueryResourceManager, self).__init__(ctx, data)
        self.source = self.get_source(self.source_type)

    def get_permissions(self):
        return self.source.get_permissions()

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
        cache_key = self.get_cache_key(q)
        resources = None

        if self._cache.load():
            resources = self._cache.get(cache_key)
            if resources is not None:
                self.log.debug("Using cached %s: %d" % (
                    "%s.%s" % (self.__class__.__module__,
                               self.__class__.__name__),
                    len(resources)))

        if resources is None:
            with self.ctx.tracer.subsegment('resource-fetch'):
                resources = self._fetch_resources(q)
            self._cache.save(cache_key, resources)

        self._cache.close()
        resource_count = len(resources)
        with self.ctx.tracer.subsegment('filter'):
            resources = self.filter_resources(resources)

        # Check resource limits if we're the current policy execution.
        if self.data == self.ctx.policy.data:
            self.check_resource_limit(len(resources), resource_count)
        return resources

    def check_resource_limit(self, selection_count, population_count):
        """Check if policy's execution affects more resources then its limit.
        """
        p = self.ctx.policy
        max_resource_limits = MaxResourceLimit(p, selection_count, population_count)
        return max_resource_limits.check_resource_limits()

    def _fetch_resources(self, query):
        try:
            return self.augment(self.source.get_resources(query)) or []
        except HttpError as e:
            error_reason, error_code, error_message = extract_errors(e)

            if error_reason is None and error_code is None:
                raise
            if error_code == 403 and 'disabled' in error_message:
                log.warning(error_message)
                return []
            elif error_reason == 'accessNotConfigured':
                log.warning(
                    "Resource:%s not available -> Service:%s not enabled on %s",
                    self.type,
                    self.resource_type.service,
                    local_session(self.session_factory).get_default_project())
                return []
            raise

    def augment(self, resources):
        return resources

    def get_urns(self, resources):
        """Generate URNs for the resources.

        A Uniform Resource Name (URN) is a URI that identifies a resource by
        name in a particular namespace. A URN may be used to talk about a
        resource without implying its location or how to access it.

        The generated URNs can uniquely identify any given resource.

        The generated URN is intended to follow a similar pattern to ARN, but be
        specific to GCP.

        gcp:<service>:<region>:<project>:<resource-type>/<resource-id>

        If the region is "global" then it is omitted from the URN.
        """
        return self.resource_type.get_urns(
            resources, local_session(self.session_factory).project_id)


class ChildResourceManager(QueryResourceManager):

    def get_resource(self, resource_info):
        child_instance = super(ChildResourceManager, self).get_resource(resource_info)

        parent_resource = self.resource_type.parent_spec['resource']
        parent_instance = self.get_resource_manager(parent_resource).get_resource(
            self._get_parent_resource_info(child_instance)
        )

        annotation_key = self.resource_type.get_parent_annotation_key()
        child_instance[annotation_key] = parent_instance

        return child_instance

    def _fetch_resources(self, query):
        if not query:
            query = {}

        resources = []
        annotation_key = self.resource_type.get_parent_annotation_key()
        parent_query = self.get_parent_resource_query()
        parent_resource_manager = self.get_resource_manager(
            resource_type=self.resource_type.parent_spec['resource'],
            data=({'query': parent_query} if parent_query else {})
        )

        for parent_instance in parent_resource_manager.resources():
            query.update(self._get_child_enum_args(parent_instance))
            children = super(ChildResourceManager, self)._fetch_resources(query)

            for child_instance in children:
                child_instance[annotation_key] = parent_instance

            resources.extend(children)

        return resources

    def _get_parent_resource_info(self, child_instance):
        mappings = self.resource_type.parent_spec['parent_get_params']
        return self._extract_fields(child_instance, mappings)

    def _get_child_enum_args(self, parent_instance):
        mappings = self.resource_type.parent_spec['child_enum_params']
        return self._extract_fields(parent_instance, mappings)

    def get_parent_resource_query(self):
        parent_spec = self.resource_type.parent_spec
        enabled = parent_spec['use_child_query'] if 'use_child_query' in parent_spec else False
        if enabled and 'query' in self.data:
            return self.data.get('query')

    @staticmethod
    def _extract_fields(source, mappings):
        result = {}

        for mapping in mappings:
            result[mapping[1]] = jmespath.search(mapping[0], source)
            # Support for regex in child_enum_params.
            # Without this support you could only map parent-child elements with the raw data
            # they hold, but with regex you could regex that data as well while you map.
            if 'regex' in mapping:
                result[mapping[1]] = re.search(mapping[3], result[mapping[1]]).group(1)

        return result


class RegionalResourceManager(ChildResourceManager):

    def get_parent_resource_query(self):
        query = None
        if self.config.regions and 'all' not in self.config.regions:
            query = [{'name': r} for r in self.config.regions]
        elif self.config.region:
            query = [{'name': self.config.region}]
        return query


class TypeMeta(type):

    def __repr__(cls):
        return "<TypeInfo service:%s component:%s scope:%s version:%s>" % (
            cls.service,
            cls.component,
            cls.scope,
            cls.version)


class TypeInfo(metaclass=TypeMeta):

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
    # for get methods that require the full event payload
    get_requires_event = False
    perm_service = None
    permissions = ()

    labels = False
    labels_op = 'setLabels'

    # required for reporting
    id = None
    name = None
    default_report_fields = ()

    # cloud asset inventory type
    asset_type = None

    # URN generation
    urn_region_key = 'region'
    # A jmespath into the resource object to find the id element of the URN.
    # If unset, it uses the value for id.
    urn_id_path = None
    # It is frequent enough that the id we want for the URN is made up of one or more
    # path segments from the id. Ids are frequently '/' delimited strings.
    # If set, this should be an iterable of integer indices into the segments.
    urn_id_segments = None
    # By default the component is taken for the URN. Can be overridden by specifying
    # a specific urn_component.
    urn_component = None
    # Truly global resources should override this to the empty string.
    urn_has_project = True
    # The location element is a zone, not a region.
    urn_zonal = False

    # If the type supports refreshing an individual resource
    refresh = None

    # Some resources don't support monitoring (and hence, no filtering).
    # Assume they generally can, and flip this to `False` for those that don't.
    allow_metrics_filters = True

    @classmethod
    def get_metric_resource_name(cls, resource):
        return resource.get(cls.name)

    @classmethod
    def get_urns(cls, resources, project_id):
        """Generate URNs for the resources.

        A Uniform Resource Name (URN) is a URI that identifies a resource by
        name in a particular namespace. A URN may be used to talk about a
        resource without implying its location or how to access it.

        The generated URNs can uniquely identify any given resource.

        The generated URN is intended to follow a similar pattern to ARN, but be
        specific to GCP.

        gcp:<service>:<location>:<project>:<resource-type>/<resource-id>

        If the region is "global" then it is omitted from the URN.
        """
        return [cls._get_urn(r, project_id) for r in resources]

    @classmethod
    def _get_urn(cls, resource, project_id) -> str:
        "Generate an URN for the resource."
        location = cls._get_location(resource)
        if location == "global":
            location = ""
        id = cls._get_urn_id(resource)
        if not cls.urn_has_project:
            project_id = ""
        # NOTE: not sure whether to use `component` or just the last part of
        # `component` (split on '.') for the part after project
        return f"gcp:{cls.service}:{location}:{project_id}:{cls.urn_component}/{id}"

    @classmethod
    def _get_urn_id(cls, resource):
        path = cls.urn_id_path
        if path is None:
            path = cls.id
        id = jmespath_search(path, resource)
        if cls.urn_id_segments:
            parts = id.split('/')
            id = '/'.join([parts[index] for index in cls.urn_id_segments])
        return id

    @classmethod
    def _get_location(cls, resource):
        """Get the region for a single resource.

        Resources are either global, regional, or zonal. When a resource is
        is zonal, the region is determined from the zone.
        """
        if cls.urn_zonal and "zone" in resource:
            zone = resource["zone"].rsplit("/", 1)[-1]
            return zone

        if cls.urn_region_key in resource:
            return resource[cls.urn_region_key].rsplit("/", 1)[-1]

        return "global"


class ChildTypeInfo(TypeInfo):

    parent_spec = None

    @classmethod
    def get_parent_annotation_key(cls):
        parent_resource = cls.parent_spec['resource']
        return 'c7n:{}'.format(parent_resource)

    @classmethod
    def get_parent(cls, resource):
        "Return the annotated parent resource."
        return resource[cls.get_parent_annotation_key()]


ERROR_REASON = jmespath_compile('error.errors[0].reason')
ERROR_CODE = jmespath_compile('error.code')
ERROR_MESSAGE = jmespath_compile('error.message')


def extract_errors(e):
    try:
        edata = json.loads(e.content)
    except Exception:
        edata = None

    return ERROR_REASON.search(edata), ERROR_CODE.search(edata), ERROR_MESSAGE.search(edata)


class GcpLocation:
    """
    The `_locations` dict is formed by the string keys representing locations taken from
    `KMS <https://cloud.google.com/kms/docs/reference/rest/v1/projects.locations/list>`_ and
    `App Engine <https://cloud.google.com/appengine/docs/admin-api/reference/rest/v1
    /apps.locations/list>`_ and list values containing the string names of the services
    the locations are available for.
    """
    _locations = {'eur4': ['kms'],
                  'global': ['kms'],
                  'europe-west4': ['kms'],
                  'asia-east2': ['appengine', 'kms'],
                  'asia-east1': ['kms'],
                  'asia': ['kms'],
                  'europe-north1': ['kms'],
                  'us-central1': ['kms'],
                  'nam4': ['kms'],
                  'asia-southeast1': ['kms'],
                  'europe': ['kms'],
                  'australia-southeast1': ['appengine', 'kms'],
                  'us-central': ['appengine'],
                  'asia-south1': ['appengine', 'kms'],
                  'us-west1': ['kms'],
                  'us-west2': ['appengine', 'kms'],
                  'asia-northeast2': ['appengine', 'kms'],
                  'asia-northeast1': ['appengine', 'kms'],
                  'europe-west2': ['appengine', 'kms'],
                  'europe-west3': ['appengine', 'kms'],
                  'us-east4': ['appengine', 'kms'],
                  'europe-west1': ['kms'],
                  'europe-west6': ['appengine', 'kms'],
                  'us': ['kms'],
                  'us-east1': ['appengine', 'kms'],
                  'northamerica-northeast1': ['appengine', 'kms'],
                  'europe-west': ['appengine'],
                  'southamerica-east1': ['appengine', 'kms']}

    @classmethod
    def get_service_locations(cls, service):
        """
        Returns a list of the locations that have a given service in associated value lists.

        :param service: a string representing the name of a service locations are queried for
        """
        return [location for location in GcpLocation._locations
                if service in GcpLocation._locations[location]]
