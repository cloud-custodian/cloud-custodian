# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import MaxResourceLimit, TypeInfo, sources
from c7n.utils import local_session
from snowflake.core.exceptions import NotFoundError, UnauthorizedError

from c7n_snowflake.actions.tags import SnowflakeTagAction


class ResourceQuery:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def filter(self, resource_manager, **params):
        """Query a set of resources"""
        session = resource_manager.get_session()
        return getattr(session, resource_manager.client)


@sources.register("describe")
class DescribeSource:
    def __init__(self, manager):
        self.manager = manager
        self.query = ResourceQuery(manager.session_factory)

    def get_resources(self, query=None):
        resources = []
        for i in self.query.filter(self.manager).iter():
            resources.append(i.to_dict())
        return resources

    def augment(self, resources):
        return resources


class QueryMeta(type):
    """metaclass to have consistent action/filter registry for new resources."""

    def __new__(cls, name, parents, attrs):
        if "filter_registry" not in attrs:
            attrs["filter_registry"] = FilterRegistry("%s.filters" % name.lower())
        if "action_registry" not in attrs:
            attrs["action_registry"] = ActionRegistry("%s.actions" % name.lower())

        if attrs.get('taggable'):
            attrs['action_registry'].register('tag', SnowflakeTagAction)

        return super(QueryMeta, cls).__new__(cls, name, parents, attrs)


class QueryResourceManager(ResourceManager, metaclass=QueryMeta):
    """
    A Snowflake Resource
    """
    type: str
    resource_type: "TypeInfo"
    source_mapping = sources
    taggable: bool

    def __init__(self, ctx, data):
        super(QueryResourceManager, self).__init__(ctx, data)
        self.source = self.get_source()

    def get_source(self):
        return self.source_mapping.get("describe")(self)

    def get_client(self):
        return getattr(self.get_session(), self.client)

    def get_session(self):
        return local_session(self.session_factory)

    def resources(self):
        resources = {}
        self._cache.load()

        with self.ctx.tracer.subsegment("resource-fetch"):
            resources = self.augment(self.source.get_resources(query=None))

        resource_count = len(resources)

        with self.ctx.tracer.subsegment("filter"):
            resources = self.filter_resources(resources)

        if self.data == self.ctx.policy.data:
            self.check_resource_limit(len(resources), resource_count)

        return resources

    def check_resource_limit(self, selection_count, population_count):
        p = self.ctx.policy
        max_resource_limits = MaxResourceLimit(p, selection_count, population_count)
        return max_resource_limits.check_resource_limits()

    def get_tag_query(self, tag_database, resource):
        name = resource["name"]
        tag_query = f"""
        select * from table({tag_database}.information_schema.TAG_REFERENCES('%s', '%s'));
        """ % (
            name,
            self.object_domain,
        )
        return tag_query

    def augment(self, resources):
        root = self.session_factory()
        tag_database = os.environ.get("SNOWFLAKE_TAG_DATABASE")

        if not tag_database:
            self.log.info("Missing tag database, skipping tag augmentation")
            return resources

        session = root.session

        try:
            session.use_database(tag_database)
        except (NotFoundError, UnauthorizedError):
            return resources

        for r in resources:
            # for ergonomics we expose both the raw tag values as well as the tags
            # in a key value pair form
            r.setdefault("tags_raw", [])
            r.setdefault("tags", {})

            query = session.sql(self.get_tag_query(tag_database, r))
            iterator = query.to_local_iterator()
            for tag_row in iterator:
                tag_dict = tag_row.as_dict()
                r['tags_raw'].append(tag_dict)
                r['tags'][tag_dict['TAG_NAME']] = tag_dict['TAG_VALUE']

        return resources
