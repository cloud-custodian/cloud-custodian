# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo


@resources.register('snowball-cluster')
class SnowballCluster(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'snowball'
        enum_spec = ('list_clusters', 'ClusterListEntries', None)
        detail_spec = (
            'describe_cluster', 'ClusterId', 'ClusterId', 'ClusterMetadata')
        id = 'ClusterId'
        name = 'Description'
        date = 'CreationDate'
        arn = False


@resources.register('snowball')
class Snowball(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'snowball'
        enum_spec = ('list_jobs', 'JobListEntries', None)
        detail_spec = (
            'describe_job', 'JobId', 'JobId', 'JobMetadata')
        id = 'JobId'
        name = 'Description'
        date = 'CreationDate'
        arn = False
