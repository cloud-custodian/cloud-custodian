# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import PolicyValidationError
from c7n_gcp.provider import resources
from c7n_gcp.query import (
    QueryResourceManager,
    TypeInfo,
    ChildTypeInfo,
    ChildResourceManager,
)


@resources.register('firestore-database')
class FirestoreDatabase(QueryResourceManager):
    """GCP resource: https://cloud.google.com/firestore/docs/reference/rest/v1/projects.databases

    :example:

    .. code-block:: yaml

        policies:
          - name: firestore-databases-in-us-east1
            resource: gcp.firestore-database
            filters:
              - type: value
                key: locationId
                value: us-east1
    """

    class resource_type(TypeInfo):
        service = 'firestore'
        version = 'v1'
        component = 'projects.databases'
        enum_spec = ('list', 'databases[]', None)
        scope_key = 'parent'
        scope_template = 'projects/{}'
        name = id = 'name'
        default_report_fields = ['name', 'locationId', 'type', 'createTime']
        asset_type = 'firestore.googleapis.com/Database'
        permissions = ('datastore.databases.list',)
        urn_component = 'database'
        urn_id_segments = (-1,)

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': resource_info['resourceName']}
            )


@resources.register('firestore-backup-schedule')
class FirestoreBackupSchedule(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/firestore/docs/reference/rest/v1/projects.databases.backupSchedules

    :example:

    .. code-block:: yaml

        policies:
          - name: firestore-backup-schedules-weekly-retention
            resource: gcp.firestore-backup-schedule
            filters:
              - type: value
                key: retention
                value: 604800s
    """

    def _get_parent_resource_info(self, child_instance):
        resource_name = None
        if child_instance.get('name'):
            resource_names = child_instance['name'].split('/backupSchedules')
            if len(resource_names) > 0:
                resource_name = resource_names[0]
        return {'resourceName': resource_name}

    class resource_type(ChildTypeInfo):
        service = 'firestore'
        version = 'v1'
        component = 'projects.databases.backupSchedules'
        enum_spec = ('list', 'backupSchedules[]', None)
        name = id = 'name'
        scope = None
        parent_spec = {
            'resource': 'firestore-database',
            'child_enum_params': [
                ('name', 'parent')
            ],
        }
        default_report_fields = ['name', 'retention', 'createTime', 'updateTime']
        permissions = ('datastore.backupSchedules.list',)
        urn_component = 'backup-schedule'
        urn_id_segments = (-1,)
        allow_metrics_filters = False

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': resource_info['resourceName']}
            )


@resources.register('firestore-index')
class FirestoreCollectionGroupIndex(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/firestore/docs/reference/rest/v1/projects.databases.collectionGroups.indexes

    :example:

    .. code-block:: yaml

        policies:
          - name: firestore-indexes-for-orders
            resource: gcp.firestore-index
            query:
              - collectionId: orders
            filters:
              - type: value
                key: queryScope
                value: COLLECTION_GROUP
    """

    def validate(self):
        if not self._get_collection_ids():
            raise PolicyValidationError(
                "gcp.firestore-index requires query with collectionId, "
                "for example: query: [{collectionId: 'orders'}]"
            )
        return self

    def _get_parent_resource_info(self, child_instance):
        resource_name = None
        if child_instance.get('name'):
            resource_names = child_instance['name'].split('/collectionGroups')
            if len(resource_names) > 0:
                resource_name = resource_names[0]
        return {'resourceName': resource_name}

    def _get_collection_ids(self):
        return [
            query['collectionId']
            for query in self.data.get('query', [])
            if query.get('collectionId')
        ]

    def _fetch_resources(self, query):
        resources = []
        annotation_key = self.resource_type.get_parent_annotation_key()
        parent_resource_manager = self.get_resource_manager(
            resource_type=self.resource_type.parent_spec['resource']
        )
        collection_ids = self._get_collection_ids()

        for parent_instance in parent_resource_manager.resources():
            for collection_id in collection_ids:
                child_query = {
                    'parent': (
                        f"{parent_instance['name']}/collectionGroups/{collection_id}"
                    )
                }
                children = QueryResourceManager._fetch_resources(self, child_query)
                for child_instance in children:
                    child_instance[annotation_key] = parent_instance
                    child_instance['c7n:collectionGroup'] = collection_id
                resources.extend(children)
        return resources

    class resource_type(ChildTypeInfo):
        service = 'firestore'
        version = 'v1'
        component = 'projects.databases.collectionGroups.indexes'
        enum_spec = ('list', 'indexes[]', None)
        name = id = 'name'
        scope = None
        parent_spec = {
            'resource': 'firestore-database',
            'child_enum_params': [
                ('name', 'parent')
            ],
        }
        default_report_fields = ['name', 'queryScope', 'state']
        permissions = ('datastore.indexes.list',)
        urn_component = 'index'
        urn_id_segments = (-1,)
        allow_metrics_filters = False

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': resource_info['resourceName']}
            )


@resources.register('firestore-field')
class FirestoreCollectionGroupField(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/firestore/docs/reference/rest/v1/projects.databases.collectionGroups.fields

    :example:

    .. code-block:: yaml

        policies:
          - name: firestore-fields-with-ttl
            resource: gcp.firestore-field
            query:
              - collectionId: orders
                filter: 'ttlConfig:*'
    """

    def validate(self):
        if not self._get_field_queries():
            raise PolicyValidationError(
                "gcp.firestore-field requires query with collectionId, "
                "for example: query: [{collectionId: 'orders', filter: 'ttlConfig:*'}]"
            )
        return self

    def _get_parent_resource_info(self, child_instance):
        resource_name = None
        if child_instance.get('name'):
            resource_names = child_instance['name'].split('/collectionGroups')
            if len(resource_names) > 0:
                resource_name = resource_names[0]
        return {'resourceName': resource_name}

    def _get_field_queries(self):
        return [
            {'collectionId': query['collectionId'], 'filter': query.get('filter')}
            for query in self.data.get('query', [])
            if query.get('collectionId')
        ]

    def _fetch_resources(self, query):
        resources = []
        annotation_key = self.resource_type.get_parent_annotation_key()
        parent_resource_manager = self.get_resource_manager(
            resource_type=self.resource_type.parent_spec['resource']
        )
        field_queries = self._get_field_queries()

        for parent_instance in parent_resource_manager.resources():
            for field_query in field_queries:
                child_query = {
                    'parent': (
                        f"{parent_instance['name']}/collectionGroups/"
                        f"{field_query['collectionId']}"
                    )
                }
                if field_query['filter']:
                    child_query['filter'] = field_query['filter']
                children = QueryResourceManager._fetch_resources(self, child_query)
                for child_instance in children:
                    child_instance[annotation_key] = parent_instance
                    child_instance['c7n:collectionGroup'] = field_query['collectionId']
                resources.extend(children)
        return resources

    class resource_type(ChildTypeInfo):
        service = 'firestore'
        version = 'v1'
        component = 'projects.databases.collectionGroups.fields'
        enum_spec = ('list', 'fields[]', None)
        name = id = 'name'
        scope = None
        parent_spec = {
            'resource': 'firestore-database',
            'child_enum_params': [
                ('name', 'parent')
            ],
        }
        default_report_fields = ['name', 'ttlConfig', 'indexConfig']
        permissions = ('datastore.indexes.list',)
        urn_component = 'field'
        urn_id_segments = (-1,)
        allow_metrics_filters = False

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': resource_info['resourceName']}
            )
