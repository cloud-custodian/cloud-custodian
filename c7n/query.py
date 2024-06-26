# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Query capability built on skew metamodel

tags_spec -> s3, elb, rds
"""
from concurrent.futures import as_completed
import functools
import itertools
import json
from typing import List

import os

from c7n.actions import ActionRegistry
from c7n.exceptions import ClientError, ResourceLimitExceeded, PolicyExecutionError
from c7n.filters import FilterRegistry, MetricsFilter
from c7n.manager import ResourceManager
from c7n.registry import PluginRegistry
from c7n.tags import register_ec2_tags, register_universal_tags, universal_augment
from c7n.utils import (
    local_session, generate_arn, get_retry, chunks, camelResource, jmespath_compile, get_path)

try:
    from botocore.paginate import PageIterator, Paginator
except ImportError:
    # Likely using another provider in a serverless environment
    class PageIterator:
        pass

    class Paginator:
        pass


class ResourceQuery:

    def __init__(self, session_factory):
        self.session_factory = session_factory

    @staticmethod
    def resolve(resource_type):
        if not isinstance(resource_type, type):
            raise ValueError(resource_type)
        else:
            m = resource_type
        return m

    def _invoke_client_enum(self, client, enum_op, params, path, retry=None):
        if client.can_paginate(enum_op):
            p = client.get_paginator(enum_op)
            if retry:
                p.PAGE_ITERATOR_CLS = RetryPageIterator
            results = p.paginate(**params)
            data = results.build_full_result()
        else:
            op = getattr(client, enum_op)
            data = op(**params)

        if path:
            path = jmespath_compile(path)
            data = path.search(data)

        return data

    def filter(self, resource_manager, **params):
        """Query a set of resources."""
        m = self.resolve(resource_manager.resource_type)
        if resource_manager.get_client:
            client = resource_manager.get_client()
        else:
            client = local_session(self.session_factory).client(
                m.service, resource_manager.config.region)
        enum_op, path, extra_args = m.enum_spec
        if extra_args:
            params = {**extra_args, **params}
        return self._invoke_client_enum(
            client, enum_op, params, path,
            getattr(resource_manager, 'retry', None)) or []

    def get(self, resource_manager, identities):
        """Get resources by identities
        """
        m = self.resolve(resource_manager.resource_type)
        params = {}
        client_filter = True

        # Try to formulate server side query in the below two scenarios
        # else fall back to client side filtering
        if m.filter_name:
            if m.filter_type == 'list':
                params[m.filter_name] = identities
                client_filter = False
            elif m.filter_type == 'scalar' and len(identities) == 1:
                params[m.filter_name] = identities[0]
                client_filter = False

        resources = self.filter(resource_manager, **params)
        if client_filter:
            # This logic was added to prevent the issue from:
            # https://github.com/cloud-custodian/cloud-custodian/issues/1398
            if all(map(lambda r: isinstance(r, str), resources)):
                resources = [r for r in resources if r in identities]
            # This logic should fix https://github.com/cloud-custodian/cloud-custodian/issues/7573
            elif all(map(lambda r: isinstance(r, tuple), resources)):
                resources = [(p, r) for p, r in resources if r[m.id] in identities]
            else:
                resources = [r for r in resources if r[m.id] in identities]

        return resources


class ChildResourceQuery(ResourceQuery):
    """A resource query for resources that must be queried with parent information.

    Several resource types can only be queried in the context of their
    parents identifiers. ie. efs mount targets (parent efs), route53 resource
    records (parent hosted zone), ecs services (ecs cluster).
    """

    capture_parent_id = False
    parent_key = 'c7n:parent-id'

    def __init__(self, session_factory, manager):
        self.session_factory = session_factory
        self.manager = manager

    def filter(self, resource_manager, parent_ids=None, **params):
        """Query a set of resources."""
        m = self.resolve(resource_manager.resource_type)
        if resource_manager.get_client:
            client = resource_manager.get_client()
        else:
            client = local_session(self.session_factory).client(m.service)

        enum_op, path, extra_args = m.enum_spec
        if extra_args:
            params.update(extra_args)

        parent_type, parent_key, annotate_parent = m.parent_spec
        parents = self.manager.get_resource_manager(parent_type)
        if not parent_ids:
            parent_ids = []
            for p in parents.resources(augment=False):
                if isinstance(p, str):
                    parent_ids.append(p)
                else:
                    parent_ids.append(p[parents.resource_type.id])

        # Bail out with no parent ids...
        existing_param = parent_key in params
        if not existing_param and len(parent_ids) == 0:
            return []

        # Handle a query with parent id
        if existing_param:
            return self._invoke_client_enum(client, enum_op, params, path)

        # Have to query separately for each parent's children.
        results = []
        for parent_id in parent_ids:
            merged_params = self.get_parent_parameters(params, parent_id, parent_key)
            subset = self._invoke_client_enum(
                client, enum_op, merged_params, path, retry=self.manager.retry)
            if annotate_parent:
                for r in subset:
                    r[self.parent_key] = parent_id
            if subset and self.capture_parent_id:
                results.extend([(parent_id, s) for s in subset])
            elif subset:
                results.extend(subset)
        return results

    def get_parent_parameters(self, params, parent_id, parent_key):
        return dict(params, **{parent_key: parent_id})


class QueryMeta(type):

    def __new__(cls, name, parents, attrs):
        if 'resource_type' not in attrs:
            return super(QueryMeta, cls).__new__(cls, name, parents, attrs)

        if 'filter_registry' not in attrs:
            attrs['filter_registry'] = FilterRegistry(
                '%s.filters' % name.lower())
        if 'action_registry' not in attrs:
            attrs['action_registry'] = ActionRegistry(
                '%s.actions' % name.lower())

        if attrs['resource_type']:
            m = ResourceQuery.resolve(attrs['resource_type'])
            # Generic cloud watch metrics support
            if m.dimension:
                attrs['filter_registry'].register('metrics', MetricsFilter)
            # EC2 Service boilerplate ...
            if m.service == 'ec2':
                # Generic ec2 resource tag support
                if getattr(m, 'taggable', True):
                    register_ec2_tags(
                        attrs['filter_registry'], attrs['action_registry'])
            if getattr(m, 'universal_taggable', False):
                compatibility = isinstance(m.universal_taggable, bool) and True or False
                register_universal_tags(
                    attrs['filter_registry'], attrs['action_registry'],
                    compatibility=compatibility)

        return super(QueryMeta, cls).__new__(cls, name, parents, attrs)


def _napi(op_name):
    return op_name.title().replace('_', '')


sources = PluginRegistry('sources')


@sources.register('describe')
class DescribeSource:

    resource_query_factory = ResourceQuery

    def __init__(self, manager):
        self.manager = manager
        self.query = self.get_query()

    def get_resources(self, ids, cache=True):
        return self.query.get(self.manager, ids)

    def resources(self, query):
        return self.query.filter(self.manager, **query)

    def get_query(self):
        return self.resource_query_factory(self.manager.session_factory)

    def get_query_params(self, query_params):
        return query_params

    def get_permissions(self):
        m = self.manager.get_model()
        prefix = m.permission_prefix or m.service
        if m.permissions_enum:
            perms = list(m.permissions_enum)
        else:
            perms = ['%s:%s' % (prefix, _napi(m.enum_spec[0]))]
        if m.universal_taggable is not False:
            perms.append("tag:GetResources")
        if m.permissions_augment:
            perms.extend(m.permissions_augment)

        if getattr(m, 'detail_spec', None):
            perms.append("%s:%s" % (prefix, _napi(m.detail_spec[0])))
        if getattr(m, 'batch_detail_spec', None):
            perms.append("%s:%s" % (prefix, _napi(m.batch_detail_spec[0])))
        return perms

    def augment(self, resources):
        model = self.manager.get_model()
        if getattr(model, 'detail_spec', None):
            detail_spec = getattr(model, 'detail_spec', None)
            _augment = _scalar_augment
        elif getattr(model, 'batch_detail_spec', None):
            detail_spec = getattr(model, 'batch_detail_spec', None)
            _augment = _batch_augment
        else:
            return resources
        if self.manager.get_client:
            client = self.manager.get_client()
        else:
            client = local_session(self.manager.session_factory).client(
                model.service, region_name=self.manager.config.region)
        _augment = functools.partial(
            _augment, self.manager, model, detail_spec, client)
        with self.manager.executor_factory(
                max_workers=self.manager.max_workers) as w:
            results = list(w.map(
                _augment, chunks(resources, self.manager.chunk_size)))
            return list(itertools.chain(*results))


class DescribeWithResourceTags(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@sources.register('describe-child')
class ChildDescribeSource(DescribeSource):

    resource_query_factory = ChildResourceQuery

    def get_query(self):
        return self.resource_query_factory(
            self.manager.session_factory, self.manager)


@sources.register('config')
class ConfigSource:

    retry = staticmethod(get_retry(('ThrottlingException',)))

    def __init__(self, manager):
        self.manager = manager
        self.titleCase = self.manager.resource_type.id[0].isupper()

    def get_permissions(self):
        return ["config:GetResourceConfigHistory",
                "config:ListDiscoveredResources"]

    def get_resources(self, ids, cache=True):
        client = local_session(self.manager.session_factory).client('config')
        results = []
        m = self.manager.get_model()
        for i in ids:
            revisions = self.retry(
                client.get_resource_config_history,
                resourceId=i,
                resourceType=m.config_type,
                limit=1).get('configurationItems')
            if not revisions:
                continue
            results.append(self.load_resource(revisions[0]))
        return list(filter(None, results))

    def get_query_params(self, query):
        """Parse config select expression from policy and parameter.

        On policy config supports a full statement being given, or
        a clause that will be added to the where expression.

        If no query is specified, a default query is utilized.

        A valid query should at minimum select fields
        for configuration, supplementaryConfiguration and
        must have resourceType qualifier.
        """
        if query and not isinstance(query, dict):
            raise PolicyExecutionError("invalid config source query %s" % (query,))

        if query is None and 'query' in self.manager.data:
            _q = [q for q in self.manager.data['query'] if 'expr' in q]
            if _q:
                query = _q.pop()

        if query is None and 'query' in self.manager.data:
            _c = [q['clause'] for q in self.manager.data['query'] if 'clause' in q]
            if _c:
                _c = _c.pop()
        elif query:
            return query
        else:
            _c = None

        s = ("select resourceId, configuration, supplementaryConfiguration "
             "where resourceType = '{}'").format(self.manager.resource_type.config_type)

        if _c:
            s += "AND {}".format(_c)

        return {'expr': s}

    def load_resource(self, item):
        item_config = self._load_item_config(item)
        resource = camelResource(
            item_config, implicitDate=True, implicitTitle=self.titleCase)
        self._load_resource_tags(resource, item)
        return resource

    def _load_item_config(self, item):
        if isinstance(item['configuration'], str):
            item_config = json.loads(item['configuration'])
        else:
            item_config = item['configuration']
        return item_config

    def _load_resource_tags(self, resource, item):
        # normalized tag loading across the many variants of config's inconsistencies.
        if 'Tags' in resource:
            return
        elif item.get('tags'):
            resource['Tags'] = [
                {u'Key': k, u'Value': v} for k, v in item['tags'].items()]
        elif item['supplementaryConfiguration'].get('Tags'):
            stags = item['supplementaryConfiguration']['Tags']
            if isinstance(stags, str):
                stags = json.loads(stags)
            if isinstance(stags, list):
                resource['Tags'] = [
                    {u'Key': t.get('key', t.get('tagKey')),
                     u'Value': t.get('value', t.get('tagValue'))}
                    for t in stags
                ]
            elif isinstance(stags, dict):
                resource['Tags'] = [{u'Key': k, u'Value': v} for k, v in stags.items()]

    def get_listed_resources(self, client):
        # fallback for when config decides to arbitrarily break select
        # resource for a given resource type.
        paginator = client.get_paginator('list_discovered_resources')
        paginator.PAGE_ITERATOR_CLS = RetryPageIterator
        pages = paginator.paginate(
            resourceType=self.manager.get_model().config_type)
        results = []

        with self.manager.executor_factory(max_workers=2) as w:
            ridents = pages.build_full_result()
            resource_ids = [
                r['resourceId'] for r in ridents.get('resourceIdentifiers', ())]
            self.manager.log.debug(
                "querying %d %s resources",
                len(resource_ids),
                self.manager.__class__.__name__.lower())

            for resource_set in chunks(resource_ids, 50):
                futures = []
                futures.append(w.submit(self.get_resources, resource_set))
                for f in as_completed(futures):
                    if f.exception():
                        self.manager.log.error(
                            "Exception getting resources from config \n %s" % (
                                f.exception()))
                    results.extend(f.result())
        return results

    def resources(self, query=None):
        client = local_session(self.manager.session_factory).client('config')
        query = self.get_query_params(query)
        pager = Paginator(
            client.select_resource_config,
            {'input_token': 'NextToken', 'output_token': 'NextToken',
             'result_key': 'Results'},
            client.meta.service_model.operation_model('SelectResourceConfig'))
        pager.PAGE_ITERATOR_CLS = RetryPageIterator

        results = []
        for page in pager.paginate(Expression=query['expr']):
            results.extend([
                self.load_resource(json.loads(r)) for r in page['Results']])

        # Config arbitrarily breaks which resource types its supports for query/select
        # on any given day, if we don't have a user defined query, then fallback
        # to iteration mode.
        if not results and query == self.get_query_params({}):
            results = self.get_listed_resources(client)
        return results

    def augment(self, resources):
        return resources


class QueryResourceManager(ResourceManager, metaclass=QueryMeta):

    resource_type = ""

    # TODO Check if we can move to describe source
    max_workers = 3
    chunk_size = 20

    _generate_arn = None

    retry = staticmethod(
        get_retry((
            'TooManyRequestsException',
            'ThrottlingException',
            'RequestLimitExceeded',
            'Throttled',
            'ThrottledException',
            'Throttling',
            'Client.RequestLimitExceeded')))

    source_mapping = sources

    def __init__(self, ctx, data):
        super(QueryResourceManager, self).__init__(ctx, data)
        self.source = self.get_source(self.source_type)

    @property
    def source_type(self):
        return self.data.get('source', 'describe')

    def get_source(self, source_type):
        if source_type in self.source_mapping:
            return self.source_mapping.get(source_type)(self)
        if source_type in sources:
            return sources[source_type](self)
        raise KeyError("Invalid Source %s" % source_type)

    @classmethod
    def has_arn(cls):
        if cls.resource_type.arn is not None:
            return bool(cls.resource_type.arn)
        elif getattr(cls.resource_type, 'arn_type', None) is not None:
            return True
        elif cls.__dict__.get('get_arns'):
            return True
        return False

    @classmethod
    def get_model(cls):
        return ResourceQuery.resolve(cls.resource_type)

    @classmethod
    def match_ids(cls, ids):
        """return ids that match this resource type's id format."""
        id_prefix = getattr(cls.get_model(), 'id_prefix', None)
        if id_prefix is not None:
            return [i for i in ids if i.startswith(id_prefix)]
        return ids

    def get_permissions(self):
        perms = self.source.get_permissions()
        if getattr(self, 'permissions', None):
            perms.extend(self.permissions)
        return perms

    def get_cache_key(self, query):
        return {
            'account': self.account_id,
            'region': self.config.region,
            'resource': str(self.__class__.__name__),
            'source': self.source_type,
            'q': query
        }

    def resources(self, query=None, augment=True) -> List[dict]:
        query = self.source.get_query_params(query)
        cache_key = self.get_cache_key(query)
        resources = None

        with self._cache:
            resources = self._cache.get(cache_key)
            if resources is not None:
                self.log.debug("Using cached %s: %d" % (
                    "%s.%s" % (self.__class__.__module__, self.__class__.__name__),
                    len(resources)))

            if resources is None:
                if query is None:
                    query = {}
                with self.ctx.tracer.subsegment('resource-fetch'):
                    resources = self.source.resources(query)
                if augment:
                    with self.ctx.tracer.subsegment('resource-augment'):
                        resources = self.augment(resources)
                    # Don't pollute cache with unaugmented resources.
                    self._cache.save(cache_key, resources)

        resource_count = len(resources)
        with self.ctx.tracer.subsegment('filter'):
            resources = self.filter_resources(resources)

        # Check if we're out of a policies execution limits.
        if self.data == self.ctx.policy.data:
            self.check_resource_limit(len(resources), resource_count)
        return resources

    def check_resource_limit(self, selection_count, population_count):
        """Check if policy's execution affects more resources then its limit.

        Ideally this would be at a higher level but we've hidden
        filtering behind the resource manager facade for default usage.
        """
        p = self.ctx.policy
        max_resource_limits = MaxResourceLimit(p, selection_count, population_count)
        return max_resource_limits.check_resource_limits()

    def _get_cached_resources(self, ids):
        key = self.get_cache_key(None)
        with self._cache:
            resources = self._cache.get(key)
            if resources is not None:
                self.log.debug("Using cached results for get_resources")
                m = self.get_model()
                id_set = set(ids)
                return [r for r in resources if r[m.id] in id_set]
        return None

    def get_resources(self, ids, cache=True, augment=True):
        if not ids:
            return []
        if cache:
            resources = self._get_cached_resources(ids)
            if resources is not None:
                return resources
        try:
            resources = self.source.get_resources(ids)
            if augment:
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
        return self.source.augment(resources)

    @property
    def account_id(self):
        """ Return the current account ID.

        This should now be passed in using the --account-id flag, but for a
        period of time we will support the old behavior of inferring this from
        IAM.
        """
        return self.config.account_id

    @property
    def region(self):
        """ Return the current region.
        """
        return self.config.region

    def get_arns(self, resources):
        arns = []

        m = self.get_model()
        arn_key = getattr(m, 'arn', None)
        if arn_key is False:
            raise ValueError("%s do not have arns" % self.type)

        for r in resources:
            if arn_key:
                arns.append(get_path(arn_key, r))
            else:
                _id = get_path(m.id, r)

                if 'arn' in _id[:3]:
                    arns.append(_id)
                else:
                    arns.append(self.generate_arn(_id))

        return arns

    @property
    def generate_arn(self):
        """ Generates generic arn if ID is not already arn format.
        """
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                self.resource_type.arn_service or self.resource_type.service,
                region=not self.resource_type.global_resource and self.config.region or "",
                account_id=self.account_id,
                resource_type=self.resource_type.arn_type,
                separator=self.resource_type.arn_separator)
        return self._generate_arn


class MaxResourceLimit:

    C7N_MAXRES_OP = os.environ.get("C7N_MAXRES_OP", 'or')

    def __init__(self, policy, selection_count, population_count):
        self.p = policy
        self.op = MaxResourceLimit.C7N_MAXRES_OP
        self.selection_count = selection_count
        self.population_count = population_count
        self.amount = None
        self.percentage_amount = None
        self.percent = None
        self._parse_policy()

    def _parse_policy(self,):
        if isinstance(self.p.max_resources, dict):
            self.op = self.p.max_resources.get("op", MaxResourceLimit.C7N_MAXRES_OP).lower()
            self.percent = self.p.max_resources.get("percent")
            self.amount = self.p.max_resources.get("amount")

        if isinstance(self.p.max_resources, int):
            self.amount = self.p.max_resources

        if isinstance(self.p.max_resources_percent, (int, float)):
            self.percent = self.p.max_resources_percent

        if self.percent:
            self.percentage_amount = self.population_count * (self.percent / 100.0)

    def check_resource_limits(self):
        if self.percentage_amount and self.amount:
            if (self.selection_count > self.amount and
               self.selection_count > self.percentage_amount and self.op == "and"):
                raise ResourceLimitExceeded(
                    ("policy:%s exceeded resource-limit:{limit} and percentage-limit:%s%% "
                     "found:{selection_count} total:{population_count}")
                    % (self.p.name, self.percent), "max-resource and max-percent",
                    self.amount, self.selection_count, self.population_count)

        if self.amount:
            if self.selection_count > self.amount and self.op != "and":
                raise ResourceLimitExceeded(
                    ("policy:%s exceeded resource-limit:{limit} "
                     "found:{selection_count} total: {population_count}") % self.p.name,
                    "max-resource", self.amount, self.selection_count, self.population_count)

        if self.percentage_amount:
            if self.selection_count > self.percentage_amount and self.op != "and":
                raise ResourceLimitExceeded(
                    ("policy:%s exceeded resource-limit:{limit}%% "
                     "found:{selection_count} total:{population_count}") % self.p.name,
                    "max-percent", self.percent, self.selection_count, self.population_count)


class ChildResourceManager(QueryResourceManager):

    child_source = 'describe-child'

    @property
    def source_type(self):
        source = self.data.get('source', self.child_source)
        if source == 'describe':
            source = self.child_source
        return source

    def get_parent_manager(self):
        return self.get_resource_manager(self.resource_type.parent_spec[0])


def _batch_augment(manager, model, detail_spec, client, resource_set):
    detail_op, param_name, param_key, detail_path, detail_args = detail_spec
    op = getattr(client, detail_op)
    if manager.retry:
        args = (op,)
        op = manager.retry
    else:
        args = ()
    kw = {param_name: [param_key and r[param_key] or r for r in resource_set]}
    if detail_args:
        kw.update(detail_args)
    response = op(*args, **kw)
    return response[detail_path]


def _scalar_augment(manager, model, detail_spec, client, resource_set):
    detail_op, param_name, param_key, detail_path = detail_spec
    op = getattr(client, detail_op)
    if manager.retry:
        args = (op,)
        op = manager.retry
    else:
        args = ()
    results = []
    for r in resource_set:
        kw = {param_name: param_key and r[param_key] or r}
        response = op(*args, **kw)
        if detail_path:
            response = response[detail_path]
        else:
            response.pop('ResponseMetadata')
        if param_key is None:
            response[model.id] = r
            r = response
        else:
            r.update(response)
        results.append(r)
    return results


class RetryPageIterator(PageIterator):

    retry = staticmethod(QueryResourceManager.retry)

    def _make_request(self, current_kwargs):
        return self.retry(self._method, **current_kwargs)


class TypeMeta(type):

    def __repr__(cls):
        if cls.config_type:
            identifier = cls.config_type
        elif cls.cfn_type:
            identifier = cls.cfn_type
        elif cls.arn_type and cls.service:
            identifier = "AWS::%s::%s" % (cls.service.title(), cls.arn_type.title())
        elif cls.enum_spec and cls.service:
            identifier = "AWS::%s::%s" % (cls.service.title(), cls.enum_spec[1])
        elif cls.service:
            identifier = "AWS::%s::%s" % (cls.service.title(), cls.id)
        else:
            identifier = cls.__name__
        return "<TypeInfo %s>" % identifier


class TypeInfo(metaclass=TypeMeta):

    """
    Resource Type Metadata


    **Required**

    :param id:  For resource types that use QueryResourceManager this field
        names the field in the enum_spec response that contains the identifier to use
        in calls to other API's of this service.
        Therefore, this "id" field might be the "arn" field for some API's but
        in other API's it's a name or other identifier value.

    :param name: Defines the name of a field in the resource that contains the "name" of
        the resource for report purposes.
        This name value appears in the "report" command output.
        By default, the id field is automatically included in the report
        and if name and id fields are the same field name then it's only shown once.
        example: custodian report --format csv  -s . my-policy.yml


    :param service: Which aws service (per sdk) has the api for this resource.
        See the "client" info for each service in the boto documentation.
        https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/index.html #noqa

    :param enum_spec: Defines the boto3 call used to find at least basic
        details on all resource instances of the relevant type. The data per
        resource can be further enriched by a supplying a detail_spec function.

        enum_spec is also used when we've received an event in which
        case the results from enum_spec are filtered to include only
        those identified by the event. If the enum function API allows a filter param to be
        specified then the filtering can be done on the server
        side.

        For instance, ASG uses "describe_auto_scaling_groups"
        as the enum function and "AutoScalingGroupNames" as a filter
        param to that function so the API returns only relevant resources.
        However, it seems that most Cloud Custodian integrations
        do not use this approach. App mesh list_meshes for instance doesn't
        support filtering  ...

        https://boto3.amazonaws.com/v1/documentation/reference/services/appmesh/client/list_meshes.html

        However, if the enum op doesn't support filtering then the enum op must return all
        instances of the resource and cloud custodian will perform client side filtering.

        Params to the enum_spec:
        - enum_op - the aws api operation
        - path - JMESPATH path to the field in the response that is the collection of result objects
        - extra_args - optional eg {'maxResults': 100}

    **Permissions - Optional**

    :param permission_prefix: Permission string prefix if not service
    :param permissions_enum: Permissions for resource enumeration/get.
        Normally we autogen but in some cases we need to specify statically
    :param permissions_augment: Permissions for resource augment

    **Arn handling / generation metadata - Optional**

    :param arn: Defines a field in the resource definition that contains the ARN value, when
        the resource has an ARM..

        This value is accessed used by the 'get_arns(..)' fn on the super-class
        QueryResourceManager. This value must be a simple field name and cannot be a path.

        If this value is not defined then 'get_arns' contains fallback logic.
        - First fallback logic is to look at what's defined in the 'id' field of the resource.
        If the value of the "id" field starts with "arn:" then that value is used as the arn.
        - Otherwise, an attempt at generating (guessing!) the ARN by assembling it from
        various fields and runtime values based on a recipe defined in 'generate_arn()' on
        the super-class QueryResourceManager.

        If you aren't going to define the "arn" field and can't rely on the "id" to be an
        ARN then you might get lucky that "generate_arn" works for your resource type.
        However, failing that then you should override "get_arns" function entirely and
        implement your own logic.

        Testing: Whatever approach you use (above) you REALLY SHOULD (!!!) include a unit
        test that verifies that "get_arns" yields the right shape of ARNs for your resources.
        This test should be implemented as an additional assertion within the unit tests
        you'll be already planning to write.

    :param arn_type: Type, used for arn construction. also required for universal tag augment
        Only required when you are NOT providing the ARN value directly via the "arn" cfg field.
        When arn is not provided then QueryResourceManager.generate_arn uses the arn_type value,
        plus other fields, to construct an ARN; basically, a best guess but not 100% reliable.
        If generate_arn() isn't good enough for your needs then you should override the
        QueryResourceManager.get_arn() function and do it yourself.

    :param arn_separator: How arn type is separated from rest of arn
    :param arn_service: For services that need custom labeling for arns

    **Resource retrieval - Optional**

    :param filter_name: When fetching a single resource via enum_spec this is technically optional,
        but effectively required for serverless event policies else we have to enumerate the
        population
    :param filter_type: filter_type, scalar or list
    :param detail_spec: Used to enrich the resource descriptions returned by enum_spec.
        In many cases the enum_spec function is one of the
        describe style functions that return a fullish spec that
        is sufficient for the user policy. However, in other cases
        the enum_spec is a list style function then the
        response to then enum call will be lacking in detail and
        might even just be a list of id's. In these cases it is generally
        necessary to define a "detail_spec" function that may be called for each id returned
        by the enum_spec which can be used to enrich the values provided by the enum_spec.

        Params to the detail_spec:
        - detail_op - the boto api call name
        - param_name - name of the identifier argument in the boto api call
        - param_key - name of field in enum_spec response tha that will be pushed into
        the identifier argument of the boto api call.
        - detail_path - path to extract from the boto response and merge into the resource model.
        if not provided then whole response is merged into the results

    :param batch_detail_spec: Used when the api supports getting resource details enmasse

    **Misc - Optional**

    :param default_report_fields: Used for reporting, array of fields
    :param date: Latest date associated to resource, generally references either create date or
        modified date. If this field is defined then it will appear in report output
        such as you would get from ....
        example: custodian report --format csv  -s . my-policy.yml

    :param dimension: Defines that resource has cloud watch metrics and the resource id can be
        passed as this value. Further customizations of dimensions require subclass metrics filter

    :param cfn_type: AWS Cloudformation type.
        See https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html

    :param config_type: AWS Config Service resource type name.
        See https://docs.aws.amazon.com/config/latest/developerguide/resource-config-reference.html
        Typically cfn_type and config_type will have the sane value,
        but there are some exceptions, so check.
        The constants defined will be verified by the PolicyMetaLint tests during the build.


    :param config_id: Resource attribute that maps to the resourceId field in AWS Config. Intended
        for resources which use one ID attribute for service API calls and a different one for
        AWS Config (example: IAM resources).

    :param universal_taggable: Determined whether resource group tagging will be used to
        augment the resource model, in which case we'll automatically register tag actions/filters.
        Note:
        - values of False will disable tag filters/actions,
        - values of True will register legacy tag filters/actions,
        - values of object() will just register current standard tag/filters/actions.

    :param global_resource: Denotes if this resource exists across all regions (iam, cloudfront,
        r53)
    :param metrics_namespace: Generally we utilize a service to namespace mapping in the metrics
        filter. However, some resources have a type specific namespace (ig. ebs)
    :param id_prefix: Specific to ec2 service resources used to disambiguate a resource by its id

    """

    # Required
    id = None
    name = None
    service = None
    enum_spec = None

    # Permissions
    permission_prefix = None
    permissions_enum = None
    permissions_augment = None

    # Arn handling / generation metadata
    arn = None
    arn_type = None
    arn_separator = "/"
    arn_service = None

    # Resource retrieval
    filter_name = None
    filter_type = None
    detail_spec = None
    batch_detail_spec = None

    # Misc
    default_report_fields = ()
    date = None
    dimension = None
    cfn_type = None
    config_type = None
    config_id = None
    universal_taggable = False
    global_resource = False
    metrics_namespace = None
    id_prefix = None
