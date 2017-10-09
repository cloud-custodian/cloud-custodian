# Copyright 2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


@resources.register('snowball-cluster')
class SnowballCluster(QueryResourceManager):

    class resource_type(object):
        service = 'snowball'
        enum_spec = ('list_clusters', 'ClusterListEntries', None)
        detail_spec = (
            'describe_cluster', 'ClusterId', 'ClusterId', 'ClusterMetadata')
        id = 'ClusterId'
        name = 'Description'
        date = 'CreationDate'
        dimension = None
        filter_name = None


@resources.register('snowball')
class Snowball(QueryResourceManager):

    class resource_type(object):
        service = 'snowball'
        enum_spec = ('list_jobs', 'JobListEntries', None)
        detail_spec = (
            'describe_job', 'JobId', 'JobId', 'JobMetadata')
        id = 'JobId'
        name = 'Description'
        date = 'CreationDate'
        dimension = None
        filter_name = None
