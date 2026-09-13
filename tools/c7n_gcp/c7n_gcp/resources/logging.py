# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from collections import defaultdict

from c7n.utils import local_session, type_schema
from c7n.filters.core import Filter, ValueFilter

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.utils import canonicalize_cloud_logging_filter, cloud_logging_filters_overlap

# TODO .. folder, billing account, org sink
# how to map them given a project level root entity sans use of c7n-org


@resources.register('log-project-sink')
class LogProjectSink(QueryResourceManager):
    """
    https://cloud.google.com/logging/docs/reference/v2/rest/v2/projects.sinks
    """

    class resource_type(TypeInfo):
        service = 'logging'
        version = 'v2'
        component = 'projects.sinks'
        enum_spec = ('list', 'sinks[]', None)
        scope_key = 'parent'
        scope_template = 'projects/{}'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "destination", "filter", "writerIdentity", "createTime"]
        asset_type = "logging.googleapis.com/LogSink"
        urn_component = "project-sink"

        @staticmethod
        def get(client, resource_info):
            return client.execute_query('get', {
                'sinkName': 'projects/{project_id}/sinks/{name}'.format(
                    **resource_info)})


@LogProjectSink.filter_registry.register('bucket')
class LogProjectSinkBucketFilter(ValueFilter):
    """
    Allows filtering on the bucket targeted by the log sink. If the sink does not target a bucket
    it does not match this filter.

    https://cloud.google.com/logging/docs/reference/v2/rest/v2/projects.sinks
    https://cloud.google.com/storage/docs/json_api/v1/buckets#resource

    :example:

    Find Sinks that target a bucket which is not using Bucket Lock

    .. code-block:: yaml

        policies:
          - name: sink-target-bucket-not-locked
            resource: gcp.log-project-sink
            filters:
              - type: bucket
                key: retentionPolicy.isLocked
                op: ne
                value: true

    """

    schema = type_schema('bucket', rinherit=ValueFilter.schema)
    permissions = ('storage.buckets.get',)
    cache_key = 'c7n:bucket'

    def __call__(self, sink):
        # no match if the target is not a bucket
        if not sink['destination'].startswith('storage.googleapis.com'):
            return False

        if self.cache_key not in sink:
            bucket_name = sink['destination'].rsplit('/', 1)[-1]

            session = local_session(self.manager.session_factory)
            client = session.client('storage', 'v1', 'buckets')
            bucket = client.execute_command('get', {'bucket': bucket_name})

            sink[self.cache_key] = bucket

        # call value filter on the bucket object
        return super().__call__(sink[self.cache_key])


class LogProjectSinkRelationshipFilterBase(Filter):
    """Reusable base for sink relationship filters (exact/overlap)."""

    annotation_key = 'c7n:matched-sinks'
    permissions = ('logging.sinks.list',)

    def _normalize_filter(self, sink):
        sink_filter = sink.get('filter')
        if not sink_filter:
            return 'true'
        return canonicalize_cloud_logging_filter(sink_filter)

    def _iter_candidate_sinks(self, resources):
        for sink in resources:
            if sink.get('disabled', False):
                continue
            destination = sink.get('destination')
            yield destination, sink

    def _iter_matched_groups(self, relation_groups):
        raise NotImplementedError(  # pragma: no cover
            "subclass must implement _iter_matched_groups"
        )

    def _annotate_group(self, sinks):
        sink_names = [s.get('name') for s in sinks if s.get('name')]
        for sink in sinks:
            sink[self.annotation_key] = [
                n for n in sink_names if n != sink.get('name')
            ]

    def process(self, resources, event=None):
        destination_groups = defaultdict(lambda: defaultdict(list))

        for destination, sink in self._iter_candidate_sinks(resources):
            destination_groups[destination][self._normalize_filter(sink)].append(sink)

        matched = []
        for relation_groups in destination_groups.values():
            for sinks in self._iter_matched_groups(relation_groups):
                self._annotate_group(sinks)
                matched.extend(sinks)
        return matched


@LogProjectSink.filter_registry.register('sink-exact')
class LogProjectSinkExactFilter(LogProjectSinkRelationshipFilterBase):
    """Match enabled sinks that share an identical effective routing filter with
    at least one other enabled sink targeting the same destination.

    Filter strings are canonicalized before comparison so that logically
    equivalent expressions (e.g. different field orderings) are treated as
    duplicates.  Disabled sinks are ignored.

    :example:

    Find all project sinks that are exact duplicates of another sink:

    .. code-block:: yaml

        policies:
          - name: gcp-log-project-sink-exact-duplicates
            resource: gcp.log-project-sink
            filters:
              - type: sink-exact

    """

    schema = type_schema('sink-exact')

    def _iter_matched_groups(self, relation_groups):
        for sinks in relation_groups.values():
            if len(sinks) > 1:
                yield sinks


@LogProjectSink.filter_registry.register('sink-overlap')
class LogProjectSinkOverlapFilter(LogProjectSinkRelationshipFilterBase):
    """Match enabled sinks whose effective routing filter overlaps with at least
    one other enabled sink targeting the same destination.

    Two filters overlap when they can both match the same log entry.  The
    analyser uses canonicalized filter expressions and understands equality,
    inequality, and numeric/severity range constraints.  Filters containing
    complex logic (OR, NOT) are conservatively treated as non-overlapping to
    avoid false positives.  Disabled sinks are ignored.

    :example:

    Find all project sinks whose log routing overlaps with a sibling sink:

    .. code-block:: yaml

        policies:
          - name: gcp-log-project-sink-overlapping
            resource: gcp.log-project-sink
            filters:
              - type: sink-overlap

    """

    schema = type_schema('sink-overlap')

    def _iter_matched_groups(self, relation_groups):
        relation_items = list(relation_groups.items())

        matched_indexes = set()
        adjacency = {idx: set() for idx in range(len(relation_items))}

        for idx, (_expr, sinks) in enumerate(relation_items):
            if len(sinks) > 1:
                matched_indexes.add(idx)

        for left in range(len(relation_items)):
            left_expression = relation_items[left][0]
            for right in range(left + 1, len(relation_items)):
                right_expression = relation_items[right][0]
                if not self._filters_overlap(left_expression, right_expression):
                    continue
                matched_indexes.update((left, right))
                adjacency[left].add(right)
                adjacency[right].add(left)

        visited = set()
        for idx in sorted(matched_indexes):
            if idx in visited:
                continue
            queue = [idx]
            component = []
            while queue:
                current = queue.pop()
                if current in visited:
                    continue
                visited.add(current)
                component.append(current)
                queue.extend(adjacency[current] - visited)
            sinks = []
            for entry_idx in component:
                sinks.extend(relation_items[entry_idx][1])
            if len(sinks) > 1:
                yield sinks

    def _filters_overlap(self, left_expression, right_expression):
        return cloud_logging_filters_overlap(left_expression, right_expression)


@LogProjectSink.action_registry.register('delete')
class DeletePubSubTopic(MethodAction):

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, m, r):
        session = local_session(self.manager.session_factory)
        project = session.get_default_project()
        return {'sinkName': 'projects/{}/sinks/{}'.format(project, r['name'])}


@resources.register('log-project-metric')
class LogProjectMetric(QueryResourceManager):
    """
    https://cloud.google.com/logging/docs/reference/v2/rest/v2/projects.metrics
    """
    class resource_type(TypeInfo):
        service = 'logging'
        version = 'v2'
        component = 'projects.metrics'
        enum_spec = ('list', 'metrics[]', None)
        scope_key = 'parent'
        scope_template = 'projects/{}'
        name = id = 'name'
        default_report_fields = [
            "name", "description", "createTime", "filter"]
        asset_type = "logging.googleapis.com/LogMetric"
        permissions = ('logging.logMetrics.list',)
        urn_component = "project-metric"

        @staticmethod
        def get(client, resource_info):
            return client.execute_query('get', {
                'metricName': 'projects/{}/metrics/{}'.format(
                    resource_info['project_id'],
                    resource_info['name'].split('/')[-1],
                )})


@resources.register('log-exclusion')
class LogExclusion(QueryResourceManager):
    """
    https://cloud.google.com/logging/docs/reference/v2/rest/v2/projects.exclusions
    """
    class resource_type(TypeInfo):
        service = 'logging'
        version = 'v2'
        component = 'exclusions'
        enum_spec = ('list', 'exclusions[]', None)
        scope_key = 'parent'
        scope_template = 'projects/{}'
        name = id = 'name'
        default_report_fields = ["name", "description", "createTime", "disabled", "filter"]
        urn_component = "exclusion"

        @staticmethod
        def get(client, resource_info):
            return client.execute_query('get', {
                'name': 'projects/{project_id}/exclusions/{name}'.format(
                    **resource_info)})
