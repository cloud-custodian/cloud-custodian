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
from c7n.exceptions import PolicyExecutionError
from c7n.filters import MetricsFilter, ValueFilter
from c7n.manager import resources
from c7n.utils import local_session, chunks, get_retry, type_schema, group_by
from c7n import query


def ecs_tag_normalize(resources):
    """normalize tag format on ecs resources to match common aws format."""
    for r in resources:
        if 'tags' in r:
            r['Tags'] = [{'Key': t['key'], 'Value': t['value']} for t in r['tags']]
            r.pop('tags')


NEW_ARN_STYLE = ('container-instance', 'service', 'task')


def ecs_taggable(model, r):
    # Tag support requires new arn format
    # https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-using-tags.html
    #
    # New arn format details
    # https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-resource-ids.html
    #
    path_parts = r[model.id].rsplit(':', 1)[-1].split('/')
    if path_parts[0] not in NEW_ARN_STYLE:
        return True
    return len(path_parts) > 2


@resources.register('ecs')
class ECSCluster(query.QueryResourceManager):

    class resource_type(object):
        service = 'ecs'
        enum_spec = ('list_clusters', 'clusterArns', None)
        batch_detail_spec = (
            'describe_clusters', 'clusters', None, 'clusters', {'include': ['TAGS']})
        name = "clusterName"
        id = "clusterArn"
        dimension = None
        filter_name = None

    def augment(self, resources):
        resources = super(ECSCluster, self).augment(resources)
        ecs_tag_normalize(resources)
        return resources


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

    def get_resources(self, ids, cache=True):
        """Retrieve ecs resources for serverless policies or related resources

        Requires arns in new format.
        https://docs.aws.amazon.com/AmazonECS/latest/userguide/ecs-resource-ids.html
        """
        cluster_resources = {}
        for i in ids:
            _, ident = i.rsplit(':', 1)
            parts = ident.split('/', 2)
            if len(parts) != 3:
                raise PolicyExecutionError("New format ecs arn required")
            cluster_resources.setdefault(parts[1], []).append(parts[2])

        results = []
        client = local_session(self.manager.session_factory).client('ecs')
        for cid, resource_ids in cluster_resources.items():
            results.extend(
                self.process_cluster_resources(client, cid, resource_ids))
        return results

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
                    include=['TAGS'],
                    services=service_set).get('services', []))
        ecs_tag_normalize(results)
        return results


@resources.register('ecs-service')
class Service(query.ChildResourceManager):

    chunk_size = 10

    class resource_type(object):
        service = 'ecs'
        name = 'serviceName'
        id = 'serviceArn'
        enum_spec = ('list_services', 'serviceArns', None)
        parent_spec = ('ecs', 'cluster', None)
        dimension = None
        supports_trailevents = True
        filter_name = None

    @property
    def source_type(self):
        source = self.data.get('source', 'describe')
        if source in ('describe', 'describe-child'):
            source = 'describe-ecs-service'
        return source

    def get_resources(self, ids, cache=True, augment=True):
        return super(Service, self).get_resources(ids, cache, augment=False)


@Service.filter_registry.register('metrics')
class ServiceMetrics(MetricsFilter):

    def get_dimensions(self, resource):
        return [
            {'Name': 'ClusterName', 'Value': resource['clusterArn'].rsplit('/')[-1]},
            {'Name': 'ServiceName', 'Value': resource['serviceName']}]


class RelatedTaskDefinitionFilter(ValueFilter):

    schema = type_schema('task-definition', rinherit=ValueFilter.schema)
    permissions = ('ecs:DescribeTaskDefinition',
                   'ecs:ListTaskDefinitions')
    related_key = 'taskDefinition'

    def process(self, resources, event=None):
        task_def_ids = list({s[self.related_key] for s in resources})
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
        return super(RelatedTaskDefinitionFilter, self).process(resources)

    def __call__(self, i):
        task = self.task_defs[i[self.related_key]]
        return self.match(task)


@Service.filter_registry.register('task-definition')
class ServiceTaskDefinitionFilter(RelatedTaskDefinitionFilter):
    """Filter services by their task definitions.

    :Example:

     Find any fargate services that are running with a particular
     image in the task and delete them.

    .. code-block:: yaml

       policies:
         - name: fargate-readonly-tasks
           resource: ecs-task
           filters:
            - launchType: FARGATE
            - type: task-definition
              key: "containerDefinitions[].image"
              value: "elasticsearch/elasticsearch:6.4.3
              value_type: swap
              op: contains
           actions:
            - delete

    """


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
        for task_set in chunks(tasks, self.manager.chunk_size):
            results.extend(
                self.manager.retry(
                    client.describe_tasks,
                    cluster=cluster_id,
                    include=['TAGS'],
                    tasks=task_set).get('tasks', []))
        ecs_tag_normalize(results)
        return results


@resources.register('ecs-task')
class Task(query.ChildResourceManager):

    chunk_size = 100

    class resource_type(object):
        service = 'ecs'
        id = name = 'taskArn'
        enum_spec = ('list_tasks', 'taskArns', None)
        parent_spec = ('ecs', 'cluster', None)
        dimension = None
        supports_trailevents = True
        filter_name = None

    @property
    def source_type(self):
        source = self.data.get('source', 'describe')
        if source in ('describe', 'describe-child'):
            source = 'describe-ecs-task'
        return source

    def get_resources(self, ids, cache=True, augment=True):
        return super(Task, self).get_resources(ids, cache, augment=False)


@Task.filter_registry.register('task-definition')
class TaskTaskDefinitionFilter(RelatedTaskDefinitionFilter):
    """Filter tasks by their task definition.

    :Example:

     Find any fargate tasks that are running without read only root
     and stop them.

    .. code-block:: yaml

       policies:
         - name: fargate-readonly-tasks
           resource: ecs-task
           filters:
            - launchType: FARGATE
            - type: task-definition
              key: "containerDefinitions[].readonlyRootFilesystem"
              value: None
              value_type: swap
              op: contains
           actions:
            - stop

    """
    related_key = 'taskDefinitionArn'


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


@resources.register('ecs-container-instance')
class ContainerInstance(query.ChildResourceManager):

    chunk_size = 100

    class resource_type(object):
        service = 'ecs'
        id = name = 'containerInstance'
        enum_spec = ('list_container_instances', 'containerInstanceArns', None)
        parent_spec = ('ecs', 'cluster', None)
        dimension = None

    @property
    def source_type(self):
        source = self.data.get('source', 'describe')
        if source in ('describe', 'describe-child'):
            source = 'describe-ecs-container-instance'
        return source


@query.sources.register('describe-ecs-container-instance')
class ECSContainerInstanceDescribeSource(ECSClusterResourceDescribeSource):

    def process_cluster_resources(self, client, cluster_id, container_instances):
        results = []
        for service_set in chunks(container_instances, self.manager.chunk_size):
            r = client.describe_container_instances(
                cluster=cluster_id,
                include=['TAGS'],
                containerInstances=container_instances).get('containerInstances', [])
            # Many Container Instance API calls require the cluster_id, adding as a
            # custodian specific key in the resource
            for i in r:
                i['c7n:cluster'] = cluster_id
            results.extend(r)
        return results


@ContainerInstance.action_registry.register('set-state')
class SetState(BaseAction):
    """Updates a container instance to either ACTIVE or DRAINING

    :example:

    .. code-block:: yaml

        policies:
            - name: drain-container-instances
              resource: ecs-container-instance
              actions:
                - type: set-state
                  state: DRAINING
    """
    schema = type_schema(
        'set-state',
        state={"type": "string", 'enum': ['DRAINING', 'ACTIVE']})
    permissions = ('ecs:UpdateContainerInstancesState',)

    def process(self, resources):
        cluster_map = group_by(resources, 'c7n:cluster')
        for cluster in cluster_map:
            c_instances = [i['containerInstanceArn'] for i in cluster_map[cluster]
                if i['status'] != self.data.get('state')]
            results = self.process_cluster(cluster, c_instances)
            return results

    def process_cluster(self, cluster, c_instances):
        # Limit on number of container instance that can be updated in a single
        # update_container_instances_state call is 10
        chunk_size = 10
        client = local_session(self.manager.session_factory).client('ecs')
        for service_set in chunks(c_instances, chunk_size):
            try:
                client.update_container_instances_state(
                    cluster=cluster,
                    containerInstances=service_set,
                    status=self.data.get('state'))
            except ClientError:
                self.manager.log.warning(
                    'Failed to update Container Instances State: %s, cluster %s' %
                    (service_set, cluster))
                raise


@ContainerInstance.action_registry.register('update-agent')
class UpdateAgent(BaseAction):
    """Updates the agent on a container instance
    """

    schema = type_schema('update-agent')
    permissions = ('ecs:UpdateContainerAgent',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ecs')
        for r in resources:
            self.process_instance(
                client, r.get('c7n:cluster'), r.get('containerInstanceArn'))

    def process_instance(self, client, cluster, instance):
        try:
            client.update_container_agent(
                cluster=cluster, containerInstance=instance)
        except (client.exceptions.NoUpdateAvailableException,
                client.exceptions.UpdateInProgressException):
            return
