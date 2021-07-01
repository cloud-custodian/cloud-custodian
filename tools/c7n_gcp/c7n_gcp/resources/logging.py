# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import local_session, type_schema
from c7n.filters.core import ValueFilter

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo

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


@resources.register('bucket-access-control-list')
class BucketAccessControlList(ChildResourceManager):
    """
    GC resource: https://cloud.google.com/storage/docs/json_api/v1/bucketAccessControls/list

    :example:

    Finds storage buckets with publicly accessible Stackdriver logs

    .. code-block:: yaml

        policies:
          - name: epam-gc-public_storage_buckets_logs
            description: |
              There are Storage Buckets with publicly accessible Stackdriver logs
            resource: gcp.bucket-access-control-list
            filters:
              - type: value
                key: entity
                value: [allUsers, allAuthenticatedUsers]
                op: in
    """
    class resource_type(ChildTypeInfo):
        service = 'storage'
        version = 'v1'
        component = 'bucketAccessControls'
        scope = 'bucket'
        enum_spec = ('list', 'items[]', None)
        name = id = 'buckets'
        default_report_fields = [name, 'items']
        asset_type = 'storage.googleapis.com/Bucket'
        permissions = ('storage.buckets.list',)
        parent_spec = {
            'resource': 'log-project-sink',
            'child_enum_params': [
                ('name', 'bucket',),
            ]}

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
            if parent_instance['destination'].startswith('storage'):
                bucket = parent_instance['destination'].split('/')[1]
                query.update({'bucket': bucket})
                children = super(ChildResourceManager, self)._fetch_resources(query)
                for child_instance in children:
                    child_instance[annotation_key] = parent_instance
                    resources.append(child_instance)

        return resources


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
