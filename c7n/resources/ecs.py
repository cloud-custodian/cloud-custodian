# Copyright 2015-2017 Capital One Services, LLC
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

from c7n.filters import MetricsFilter
from c7n import query
from c7n.manager import resources
from c7n.utils import local_session, chunks


@resources.register('ecs')
class ECSCluster(query.QueryResourceManager):

    class resource_type(object):
        service = 'ecs'
        enum_spec = ('list_clusters', 'clusterArns', None)
        batch_detail_spec = (
            'describe_clusters', 'clusters', None, 'clusters')
        name = "clusterName"
        id = "clusterArn"
        dimension = None
        filter_name = None


@ECSCluster.filter_registry.register('metrics')
class ECSMetrics(MetricsFilter):

    def get_dimensions(self, resource):
        return [{'Name': 'ClusterName', 'Value': resource['clusterName']}]



@query.sources.register('describe-ecs')
class ECSDescribeSource(query.ChildDescribeSource):

    def __init__(self, manager):
        self.manager = manager
        self.query = query.ChildResourceQuery(
            self.manager.session_factory, self.manager)
        self.query.capture_parent_id = True

    def augment(self, resources):
        parent_child_map = {}
        for pid, r in resources:
            parent_child_map.setdefault(pid, []).append(r)
        results = []
        with self.manager.executor_factory(
                max_workers=self.manager.max_workers) as w:
            client = local_session(self.manager.session_factory).client('ecs')
            futures = {}
            for pid, services in parent_child_map.items():
                futures[w.submit(self.process_cluster_services, client, pid, services)] = (pid, services)
            for f in futures:
                pid, services = futures[f]
                if f.exception():
                    self.manager.log.warning('error fetching ecs services for cluster %s' % pid)
                    continue
                results.extend(f.result())
        return results

    def process_cluster_services(self, client, cluster_id, services):
        results = []
        for service_set in chunks(services, self.manager.chunk_size):
            results.extend(
                client.describe_services(
                    cluster=cluster_id,
                    services=service_set).get('services', []))
        return results


@resources.register('ecs-service')
class ECSService(query.ChildResourceManager):

    chunk_size = 10

    class resource_type(object):
        service = 'ecs'
        name = 'serviceName'
        id = 'serviceArn'
        enum_spec = ('list_services', 'serviceArns', None)
        parent_spec = ('ecs', 'cluster')
        dimension = None

    @property
    def source_type(self):
        source = self.data.get('source', 'describe')
        if source in ('describe', 'describe-child'):
            source = 'describe-ecs'
        return source



@ECSService.filter_registry.register('metrics')
class ECSServiceMetrics(MetricsFilter):

    def get_dimensions(self, resource):
        return [
            {'Name': 'ClusterName', 'Value': resource['clusterArn'].rsplit('/')[-1]},
            {'Name': 'ServiceName', 'Value': resource['serviceName']}]
