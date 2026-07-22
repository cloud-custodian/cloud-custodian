# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import re

from c7n_gcp.filters import IamPolicyFilter
from c7n_gcp.filters.iampolicy import IamPolicyValueFilter
from c7n_gcp.query import ChildResourceManager, ChildTypeInfo
from c7n_gcp.provider import resources


@resources.register('dataproc-clusters')
class DataprocClusters(ChildResourceManager):

    class resource_type(ChildTypeInfo):
        service = 'dataproc'
        version = 'v1'
        component = 'projects.regions.clusters'
        enum_spec = ('list', 'clusters[]', None)
        scope_key = 'projectId'
        name = id = 'clusterName'
        parent_spec = {
            'resource': 'region',
            'child_enum_params': {
                ('name', 'region')},
            'parent_get_params': [
                ('labels."goog-dataproc-location"', 'name'),
            ],
            'use_child_query': True,
        }
        default_report_fields = ['clusterName', 'status.state', 'status.stateStartTime']
        asset_type = "dataproc.googleapis.com/Dataproc"
        urn_component = "dataproc"
        urn_id_segments = (-1,)

        @classmethod
        def _get_location(cls, resource):
            return resource['labels']['goog-dataproc-location']

        @staticmethod
        def get(client, resource_info):
            project_id, region, cluster_name = re.match(
                'projects/(.*?)/regions/(.*?)/clusters/(.*)',
                resource_info['resourceName']).groups()
            return client.execute_query(
                'get', {'projectId': project_id,
                        'region': region,
                        'clusterName': cluster_name})


@DataprocClusters.filter_registry.register('iam-policy')
class DataprocClustersIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process dataproc cluster resources correctly.
    """
    permissions = ('dataproc.clusters.getIamPolicy',)

    def _verb_arguments(self, resource):
        return {'resource': 'projects/{}/regions/{}/clusters/{}'.format(
            resource['projectId'],
            resource['c7n:region']['name'],
            resource['clusterName'])}

    def process_resources(self, resources):
        value_filter = IamPolicyValueFilter(self.data['doc'], self.manager)
        value_filter._verb_arguments = self._verb_arguments
        return value_filter.process(resources)
