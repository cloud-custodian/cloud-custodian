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

from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.filters import MetricsFilter, ValueFilter
from c7n.manager import resources
from c7n.utils import local_session, chunks, get_retry, type_schema
from c7n import query


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


class ECSClusterResourceDescribeSource(query.ChildDescribeSource):

    # We need an additional subclass of describe for ecs cluster.
    #
    # - Default child query just returns the child resources from
    #   enumeration op, for ecs clusters, enumeration just returns
    #   resources ids, we also need to retain the parent id for
    #   augmentation.
    #
    # - The default augmentation detail_spec/batch_detail_spec need additional
    #   handling for the string resources with parent id.
    #

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
                futures[
                    w.submit(
                        self.process_cluster_resources, client, pid, services)
                ] = (pid, services)
            for f in futures:
                pid, services = futures[f]
                if f.exception():
                    self.manager.log.warning(
                        'error fetching ecs resources for cluster %s: %s',
                        pid, f.exception())
                    continue
                results.extend(f.result())
        return results


@query.sources.register('describe-ecs-service')
class ECSServiceDescribeSource(ECSClusterResourceDescribeSource):

    def process_cluster_resources(self, client, cluster_id, services):
        results = []
        for service_set in chunks(services, self.manager.chunk_size):
            results.extend(
                client.describe_services(
                    cluster=cluster_id,
                    services=service_set).get('services', []))
        return results


@resources.register('ecs-service')
class Service(query.ChildResourceManager):

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
            source = 'describe-ecs-service'
        return source


@Service.filter_registry.register('metrics')
class ServiceMetrics(MetricsFilter):

    def get_dimensions(self, resource):
        return [
            {'Name': 'ClusterName', 'Value': resource['clusterArn'].rsplit('/')[-1]},
            {'Name': 'ServiceName', 'Value': resource['serviceName']}]


@Service.filter_registry.register('task-definition')
class ServiceTaskFilter(ValueFilter):

    schema = type_schema('task-definition', rinherit=ValueFilter.schema)
    permissions = ('ecs:DescribeTaskDefinition',
                   'ecs:ListTaskDefinitions')

    def process(self, resources, event=None):
        task_def_ids = [s['taskDefinition'] for s in resources]
        task_def_manager = self.manager.get_resource_manager(
            'ecs-task-definition')

        # due to model difference (multi-level containment with
        # multi-step resource iteration) and potential volume of
        # resources, we break our abstractions a little in the name of
        # efficiency wrt api usage.

        # check to see if task def cache is already populated
        key = task_def_manager.get_cache_key(None)
        if self.manager._cache.get(key):
            task_defs = task_def_manager.get_resources(task_def_ids)
        # else just augment the ids
        else:
            task_defs = task_def_manager.augment(task_def_ids)
        self.task_defs = {t['taskDefinitionArn']: t for t in task_defs}
        return super(ServiceTaskFilter, self).process(resources)

    def __call__(self, i):
        task = self.task_defs[i['taskDefinition']]
        return self.match(task)


@Service.action_registry.register('delete')
class DeleteService(BaseAction):
    """Delete service(s)."""

    schema = type_schema('delete')
    permissions = ('ecs:DeleteService',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ecs')
        retry = get_retry(('Throttling',))
        for r in resources:
            try:
                primary = [d for d in r['deployments']
                           if d['status'] == 'PRIMARY'].pop()
                if primary['desiredCount'] > 0:
                    retry(client.update_service,
                          cluster=r['clusterArn'],
                          service=r['serviceName'],
                          desiredCount=0)
                retry(client.delete_service,
                      cluster=r['clusterArn'], service=r['serviceName'])
            except ClientError as e:
                if e.response['Error']['Code'] != 'ServiceNotFoundException':
                    raise


@query.sources.register('describe-ecs-task')
class ECSTaskDescribeSource(ECSClusterResourceDescribeSource):

    def process_cluster_resources(self, client, cluster_id, tasks):
        results = []
        for service_set in chunks(tasks, self.manager.chunk_size):
            results.extend(
                client.describe_tasks(
                    cluster=cluster_id,
                    tasks=tasks).get('tasks', []))
        return results


@resources.register('ecs-task')
class Task(query.ChildResourceManager):

    chunk_size = 100

    class resource_type(object):
        service = 'ecs'
        id = name = 'taskArn'
        enum_spec = ('list_tasks', 'taskArns', None)
        parent_spec = ('ecs', 'cluster')
        dimension = None

    @property
    def source_type(self):
        source = self.data.get('source', 'describe')
        if source in ('describe', 'describe-child'):
            source = 'describe-ecs-task'
        return source


@Task.action_registry.register('stop')
class StopTask(BaseAction):
    """Stop/Delete a currently running task."""

    schema = type_schema('stop', reason={"type": "string"})
    permissions = ('ecs:StopTask',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ecs')
        retry = get_retry(('Throttling',))
        reason = self.data.get('reason', 'custodian policy')

        for r in resources:
            try:
                retry(client.stop_task,
                      cluster=r['clusterArn'],
                      task=r['taskArn'],
                      reason=reason)
            except ClientError as e:
                # No error code for not found.
                if e.response['Error']['Message'] != "The referenced task was not found.":
                    raise


@resources.register('ecs-task-definition')
class TaskDefinition(query.QueryResourceManager):

    class resource_type(object):
        service = 'ecs'
        id = name = 'taskDefinitionArn'
        enum_spec = ('list_task_definitions', 'taskDefinitionArns', None)
        detail_spec = (
            'describe_task_definition', 'taskDefinition', None,
            'taskDefinition')
        dimension = None
        filter_name = None
        filter_type = None

    def get_resources(self, ids, cache=True):
        if cache:
            resources = self._get_cached_resources(ids)
            if resources is not None:
                return resources
        try:
            resources = self.augment(ids)
            return resources
        except ClientError as e:
            self.log.warning("event ids not resolved: %s error:%s" % (ids, e))
            return []


@TaskDefinition.action_registry.register('delete')
class DeleteTaskDefinition(BaseAction):
    """Delete/DeRegister a task definition.

    The definition will be marked as InActive. Currently running
    services and task can still reference, new services & tasks
    can't.
    """

    schema = type_schema('delete')
    permissions = ('ecs:DeregisterTaskDefinition',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ecs')
        retry = get_retry(('Throttling',))

        for r in resources:
            try:
                retry(client.deregister_task_definition,
                      taskDefinition=r['taskDefinitionArn'])
            except ClientError as e:
                # No error code for not found.
                if e.response['Error'][
                        'Message'] != 'The specified task definition does not exist.':
                    raise
