# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters import ListItemFilter
from c7n.utils import local_session, type_schema
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('vector-search-collection')
class VectorSearchCollection(QueryResourceManager):
    """Vector Search 2.0 collection

    https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search-2/reference/rest/v1/projects.locations.collections

    Metrics match on the collection id, which is only unique within a location,
    so same-named collections in different locations share metrics. Index
    metrics like ``index/replicas`` report an empty collection id, so use the
    ``index`` filter instead.

    :example:

    Collections with an index and no searches in seven days:

    .. code-block:: yaml

        policies:
          - name: vector-search-collection-unsearched
            resource: gcp.vector-search-collection
            filters:
              - type: index
              - type: metrics
                name: vectorsearch.googleapis.com/search/request_count
                aligner: ALIGN_SUM
                reducer: REDUCE_SUM
                group-by-fields:
                  - resource.labels.collection
                days: 7
                op: lte
                value: 0
                missing-value: 0
    """

    class resource_type(TypeInfo):
        service = 'vectorsearch'
        version = 'v1'
        component = 'projects.locations.collections'
        enum_spec = ('list', 'collections[]', None)
        scope_key = 'parent'
        scope_template = 'projects/{}/locations/-'
        name = id = 'name'
        default_report_fields = ['name', 'displayName', 'createTime', 'updateTime']
        permissions = ('vectorsearch.collections.list',)
        urn_component = 'collection'
        urn_id_segments = (-1,)
        metric_key = 'resource.labels.collection'
        supported_metric_keys = ('resource.labels.collection',)

        @staticmethod
        def get(client, resource_info):
            return client.execute_query('get', {'name': resource_info['resourceName']})

        @classmethod
        def _get_location(cls, resource):
            return resource['name'].split('/')[3]

        @classmethod
        def get_metric_resource_name(cls, resource, metric_key=None):
            return resource['name'].rsplit('/', 1)[-1]


@VectorSearchCollection.filter_registry.register('index')
class VectorSearchCollectionIndexFilter(ListItemFilter):
    """Filter collections by their indexes

    ``attrs`` match each index as returned by
    https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/vector-search-2/reference/rest/v1/projects.locations.collections.indexes/list

    Every index keeps at least one replica running. Use ``count: 0`` to find
    collections without an index.

    :example:

    .. code-block:: yaml

        policies:
          - name: vector-search-collection-two-replicas
            resource: gcp.vector-search-collection
            filters:
              - type: index
                attrs:
                  - type: value
                    key: dedicatedInfrastructure.autoscalingSpec.minReplicaCount
                    op: gte
                    value: 2
    """

    schema = type_schema(
        'index',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'},
    )
    schema_alias = False
    annotation_key = 'c7n:Indexes'
    annotate_items = True
    item_annotation_key = 'c7n:MatchedIndexes'
    permissions = ('vectorsearch.indexes.list',)

    def process(self, resources, event=None):
        self.client = local_session(self.manager.session_factory).client(
            'vectorsearch', 'v1', 'projects.locations.collections.indexes')
        return super().process(resources, event)

    def get_item_values(self, resource):
        if self.annotation_key not in resource:
            indexes = []
            for page in self.client.execute_paged_query('list', {'parent': resource['name']}):
                indexes.extend(page.get('indexes', ()))
            resource[self.annotation_key] = indexes
        return resource[self.annotation_key]
