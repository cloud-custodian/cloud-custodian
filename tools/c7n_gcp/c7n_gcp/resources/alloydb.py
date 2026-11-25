# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import (
    QueryResourceManager, TypeInfo, ChildTypeInfo, ChildResourceManager)


@resources.register('alloydb-cluster')
class AlloyDBCluster(QueryResourceManager):
    """GCP resource:
    https://cloud.google.com/alloydb/docs/reference/rest/v1/projects.locations.clusters
    """
    class resource_type(TypeInfo):
        service = 'alloydb'
        version = 'v1'
        component = 'projects.locations.clusters'
        enum_spec = ('list', 'clusters[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}/locations/-'
        name = id = 'name'
        default_report_fields = [
            'name', 'state', 'clusterType', 'databaseVersion', 'createTime']
        asset_type = 'alloydb.googleapis.com/Cluster'
        urn_component = 'cluster'
        urn_id_segments = (-1,)
        labels = True
        labels_op = 'patch'
        labels_perm = 'update'

        @classmethod
        def _get_location(cls, resource):
            return resource['name'].split('/')[3]

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': resource_info['resourceName']})

        @staticmethod
        def get_label_params(resource, all_labels):
            return {
                'name': resource['name'],
                'updateMask': 'labels',
                'body': {'labels': all_labels}}


@resources.register('alloydb-instance')
class AlloyDBInstance(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/alloydb/docs/reference/rest/v1/projects.locations.clusters.instances
    """
    def _get_parent_resource_info(self, child_instance):
        # instance name: projects/{p}/locations/{l}/clusters/{c}/instances/{i}
        # the parent cluster name is everything up to /instances
        return {'resourceName': child_instance['name'].split('/instances/')[0]}

    def _get_child_enum_args(self, parent_instance):
        return {'parent': parent_instance['name']}

    class resource_type(ChildTypeInfo):
        service = 'alloydb'
        version = 'v1'
        component = 'projects.locations.clusters.instances'
        enum_spec = ('list', 'instances[]', None)
        scope = 'global'
        name = id = 'name'
        parent_spec = {'resource': 'alloydb-cluster'}
        default_report_fields = [
            'name', 'state', 'instanceType', 'availabilityType', 'createTime']
        asset_type = 'alloydb.googleapis.com/Instance'
        urn_component = 'instance'
        urn_id_segments = (-1,)
        labels = True
        labels_op = 'patch'
        labels_perm = 'update'

        @classmethod
        def _get_location(cls, resource):
            return resource['name'].split('/')[3]

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': resource_info['resourceName']})

        @staticmethod
        def get_label_params(resource, all_labels):
            return {
                'name': resource['name'],
                'updateMask': 'labels',
                'body': {'labels': all_labels}}
