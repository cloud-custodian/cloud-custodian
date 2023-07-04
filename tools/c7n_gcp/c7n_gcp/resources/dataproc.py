# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

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
        name = id = 'name'
        parent_spec = {
            'resource': 'region',
            'child_enum_params': {
                ('name', 'region')},
            'use_child_query': True,
        }
        default_report_fields = ['id', 'name', 'dnsName', 'creationTime', 'visibility']
        asset_type = "dataproc.googleapis.com/Dataproc"
        urn_component = "dataproc"
        urn_id_segments = (-1,)
