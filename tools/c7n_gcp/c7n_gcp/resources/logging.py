# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from collections import defaultdict

from c7n.utils import local_session, type_schema
from c7n.filters.core import Filter, ValueFilter

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.utils import (
    CloudLoggingOverlap,
    canonicalize_cloud_logging_filter,
    compare_cloud_logging_filters,
    normalize_cloud_logging_filter_spacing,
    parse_cloud_logging_filter,
)

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


@LogProjectSink.filter_registry.register('sink-overlap')
class LogProjectSinkOverlapFilter(Filter):
    """Match enabled sinks whose effective routing filter is identical to, or
    overlaps with, at least one other enabled sink targeting the same
    destination.

    A sink's effective routing is its filter minus its enabled exclusions.
    ``match`` controls how effective routing is compared:

    - ``overlap`` (default): two sinks overlap when some log entry could match
      both.  The analyser understands AND/OR/NOT, equality, inequality, and
      numeric/severity ranges.  When a filter also uses comparisons it cannot
      evaluate, such as ``:`` and regular expression matches, global search
      terms or ``LOG_ID``, sinks that are not provably disjoint are reported
      as possible matches.
    - ``exact``: effective routing is canonicalized before comparison so that
      logically equivalent expressions (e.g. different field orderings) are
      treated as duplicates.

    Disabled sinks are ignored.  A sink whose effective routing cannot be
    parsed is logged and left out of ``overlap`` comparisons; with ``exact``
    it only matches sinks with the same filter text.  Each matched sink is
    annotated with the names of the sinks it directly matches under
    ``c7n:matched-sinks``, and with the names of the sinks it possibly matches
    under ``c7n:possible-matched-sinks``.

    Sinks are only compared with the other sinks that reach this filter, so
    filters placed before it narrow the comparison.  To compare against every
    sink in the project and then narrow the results, put ``sink-overlap``
    first.

    :example:

    Find all project sinks whose log routing overlaps, or possibly overlaps,
    with a sibling sink:

    .. code-block:: yaml

        policies:
          - name: gcp-log-project-sink-overlapping
            resource: gcp.log-project-sink
            filters:
              - type: sink-overlap

    :example:

    Find only project sinks whose overlap with a sibling sink is proven:

    .. code-block:: yaml

        policies:
          - name: gcp-log-project-sink-proven-overlap
            resource: gcp.log-project-sink
            filters:
              - type: sink-overlap
              - type: value
                key: '"c7n:matched-sinks"'
                value: not-null

    :example:

    Find all project sinks that are exact duplicates of another sink:

    .. code-block:: yaml

        policies:
          - name: gcp-log-project-sink-exact-duplicates
            resource: gcp.log-project-sink
            filters:
              - type: sink-overlap
                match: exact

    """

    schema = type_schema('sink-overlap', match={'enum': ['exact', 'overlap']})
    annotation_key = 'c7n:matched-sinks'
    possible_annotation_key = 'c7n:possible-matched-sinks'
    permissions = ('logging.sinks.list',)

    def _effective_filter(self, sink, exact):
        # A sink routes entries that match its filter and none of its
        # enabled exclusions.
        exclusions = [
            exclusion['filter']
            for exclusion in sink.get('exclusions', ())
            if not exclusion.get('disabled', False) and exclusion.get('filter')
        ]
        try:
            # Each filter is canonicalized on its own first, so unbalanced
            # parentheses can't change how the filters combine.  A filter that
            # is empty once canonicalized, e.g. only a comment, is treated
            # like a missing one.
            parts = []
            routed = canonicalize_cloud_logging_filter(sink.get('filter'))
            if routed:
                parts.append(f'({routed})')
            for exclusion in exclusions:
                excluded = canonicalize_cloud_logging_filter(exclusion)
                if excluded:
                    parts.append(f'NOT ({excluded})')
            key = canonicalize_cloud_logging_filter(' AND '.join(parts))
            # Overlap comparison parses the key again.
            parse_cloud_logging_filter(key)
            return key
        except ValueError as e:
            self.log.warning(
                f"Unable to parse effective filter of log sink {sink.get('name')}: {e}")
            if not exact:
                return None
            # Identical unparseable filters are still exact duplicates.  A
            # canonical key always parses, so this cannot collide with one.
            # Each filter is normalized on its own so a comment can't swallow
            # the ones after it.
            raw = [normalize_cloud_logging_filter_spacing(sink.get('filter'))] + [
                f'NOT ({normalize_cloud_logging_filter_spacing(e)})' for e in exclusions
            ]
            return ' AND '.join(raw)

    def process(self, resources, event=None):
        exact = self.data.get('match', 'overlap') == 'exact'
        destination_groups = defaultdict(lambda: defaultdict(list))

        for sink in resources:
            if sink.get('disabled', False):
                continue
            expression = self._effective_filter(sink, exact)
            if expression is None:
                continue
            destination_groups[sink.get('destination')][expression].append(sink)

        matched = []
        for relation_groups in destination_groups.values():
            for sink, peers, possible in self._iter_matches(relation_groups, exact):
                sink[self.annotation_key] = [p.get('name') for p in peers]
                sink[self.possible_annotation_key] = [p.get('name') for p in possible]
                matched.append(sink)
        return matched

    def _compare(self, left, right, cache):
        # Overlap is symmetric, so each pair of filters is compared once.
        pair = (left, right) if left <= right else (right, left)
        if pair not in cache:
            result = compare_cloud_logging_filters(*pair)
            # Identical effective filters route the same entries, so they
            # overlap unless the filter provably matches nothing.
            if left == right and result is CloudLoggingOverlap.POSSIBLE:
                result = CloudLoggingOverlap.OVERLAP
            cache[pair] = result
        return cache[pair]

    def _iter_matches(self, relation_groups, exact):
        # Each sink is paired with the sinks it directly matches, not with
        # everything reachable through a chain of overlaps.
        cache = {}
        for expression, sinks in relation_groups.items():
            if exact:
                results = [(sinks, CloudLoggingOverlap.OVERLAP)]
            else:
                results = [
                    (peers, self._compare(expression, other, cache))
                    for other, peers in relation_groups.items()
                ]
            for sink in sinks:
                peers, possible = [], []
                for others, result in results:
                    if result is CloudLoggingOverlap.OVERLAP:
                        peers.extend(p for p in others if p is not sink)
                    elif result is CloudLoggingOverlap.POSSIBLE:
                        possible.extend(p for p in others if p is not sink)
                if peers or possible:
                    yield sink, peers, possible


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
