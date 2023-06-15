# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import importlib
from functools import lru_cache

from .core import ValueFilter, OPERATORS
from c7n.query import ChildResourceQuery
from c7n.utils import jmespath_search


class RelatedResourceFilter(ValueFilter):

    schema_alias = False

    RelatedResource = None
    RelatedIdsExpression = None
    AnnotationKey = None
    FetchThreshold = 10

    def get_permissions(self):
        return self.get_resource_manager().get_permissions()

    def validate(self):
        name = self.__class__.__name__
        if self.RelatedIdsExpression is None:
            raise ValueError(
                "%s Filter requires resource expression" % name)
        # if self.AnnotationKey is None:
        #    raise ValueError(
        #        "%s Filter requires annotation key" % name)

        if self.RelatedResource is None:
            raise ValueError(
                "%s Filter requires resource manager spec" % name)
        return super(RelatedResourceFilter, self).validate()

    def get_related_ids(self, resources):
        return set(jmespath_search(
            "[].%s" % self.RelatedIdsExpression, resources))

    def get_related(self, resources):
        resource_manager = self.get_resource_manager()
        related_ids = self.get_related_ids(resources)
        model = resource_manager.get_model()
        if len(related_ids) < self.FetchThreshold:
            related = resource_manager.get_resources(list(related_ids))
        else:
            related = resource_manager.resources()
        return {r[model.id]: r for r in related
                if r[model.id] in related_ids}

    @lru_cache(maxsize=None)
    def get_resource_manager(self):
        mod_path, class_name = self.RelatedResource.rsplit('.', 1)
        module = importlib.import_module(mod_path)
        manager_class = getattr(module, class_name)
        return manager_class(self.manager.ctx, {})

    def process_resource(self, resource, related):
        related_ids = self.get_related_ids([resource])
        model = self.manager.get_model()
        op = self.data.get('operator', 'or')
        found = []

        if self.data.get('match-resource') is True:
            self.data['value'] = self.get_resource_value(
                self.data['key'], resource)

        if self.data.get('value_type') == 'resource_count':
            count_matches = OPERATORS[self.data.get('op')](len(related_ids), self.data.get('value'))
            if count_matches:
                self._add_annotations(related_ids, resource)
            return count_matches

        for rid in related_ids:
            robj = related.get(rid, None)
            if robj is None:
                self.log.warning(
                    "Resource %s:%s references non existant %s: %s",
                    self.manager.type,
                    resource[model.id],
                    self.RelatedResource.rsplit('.', 1)[-1],
                    rid)
                # in the event that the filter is looking specifically for absent values, we can
                # safely assume that the non-existant related resource will have an absent value at
                # any given key
                if self.data['value'] == 'absent':
                    found.append(rid)
                continue
            if self.match(robj):
                found.append(rid)

        if found:
            self._add_annotations(found, resource)

        if op == 'or' and found:
            return True
        elif op == 'and' and len(found) == len(related_ids):
            return True
        return False

    def _add_annotations(self, related_ids, resource):
        if self.AnnotationKey is not None:
            akey = 'c7n:%s' % self.AnnotationKey
            resource[akey] = list(set(related_ids).union(resource.get(akey, [])))

    def process(self, resources, event=None):
        related = self.get_related(resources)
        return [r for r in resources if self.process_resource(r, related)]


class RelatedResourceByIdFilter(RelatedResourceFilter):
    """
    Value filter for related resources in which the main resource only contains the related
    resource id.
    """

    RelatedResourceByIdExpression = None

    def get_related(self, resources):
        resource_manager = self.get_resource_manager()
        related_ids = self.get_related_ids(resources)

        related = {}
        for r in resource_manager.resources():
            matched_vpc = self.get_related_by_ids(r) & related_ids
            if matched_vpc:
                for vpc in matched_vpc:
                    related_resources = related.get(vpc, [])
                    related_resources.append(r)
                    related[vpc] = related_resources
        return related

    def get_related_by_ids(self, resources):
        RelatedResourceKey = self.RelatedResourceByIdExpression or self.RelatedIdsExpression
        ids = jmespath_search("%s" % RelatedResourceKey, resources)
        if isinstance(ids, str):
            ids = [ids]
        return set(ids)

    def process_resource(self, resource, related):
        related_ids = self.get_related_ids([resource])
        op = self.data.get('operator', 'or')
        found = []

        if self.data.get('match-resource') is True:
            self.data['value'] = self.get_resource_value(
                self.data['key'], resource)

        if self.data.get('value_type') == 'resource_count':
            count_matches = OPERATORS[self.data.get('op')](len(related_ids), self.data.get('value'))
            if count_matches:
                self._add_annotations(related_ids, resource)
            return count_matches

        for rid in related_ids:
            robjs = related.get(rid, [None])
            for robj in robjs:
                if robj is None:
                    continue
                if self.match(robj):
                    found.append(rid)

        if found:
            self._add_annotations(found, resource)

        if op == 'or' and found:
            return True
        elif op == 'and' and len(found) == len(related_ids):
            return True
        return False


class ChildResourceFilter(RelatedResourceFilter):
    ChildResource = None
    RelatedIdsExpression = None
    ChildResourceParentKey = "c7n:parent-id"

    def get_related(self, resources):
        self.child_resources = {}

        parent_ids = self.get_related_ids(resources)

        child_resource_manager = self.get_resource_manager()
        child_query = ChildResourceQuery(
            child_resource_manager.session_factory,
            child_resource_manager,
        )
        children = child_query.filter(child_resource_manager, parent_ids=list(parent_ids))
        for r in children:
            self.child_resources.setdefault(r[self.ChildResourceParentKey], []).append(r)

        return self.child_resources

    def _add_annotations(self, related_ids, resource):
        if self.AnnotationKey is not None:
            model = self.manager.get_model()
            akey = 'c7n:%s' % self.AnnotationKey
            resource[akey] = self.child_resources.get(resource[model.id], [])
