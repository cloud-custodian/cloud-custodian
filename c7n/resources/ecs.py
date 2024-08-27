# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy
from botocore.exceptions import ClientError

from c7n.actions import AutoTagUser, AutoscalingBase, BaseAction
from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n.filters import MetricsFilter, ValueFilter, Filter
from c7n.filters.costhub import CostHubRecommendation
from c7n.filters.offhours import OffHour, OnHour
import c7n.filters.vpc as net_filters
from c7n.manager import resources
from c7n.utils import local_session, chunks, get_retry, type_schema, group_by, jmespath_compile
from c7n import query, utils
from c7n.query import DescribeSource, ConfigSource
from c7n.resources.aws import Arn
from c7n.tags import Tag, TagDelayedAction, RemoveTag, TagActionFilter


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


class ContainerConfigSource(ConfigSource):

    preserve_empty = ()
    preserve_case = {'Tags'}
    mapped_keys = {}

    @classmethod
    def remap_keys(cls, resource):
        for k, v in cls.mapped_keys.items():
            if v in resource:
                continue
            if k not in resource:
                continue
            resource[v] = resource.pop(k)
        return resource

    @classmethod
    def lower_keys(cls, data):
        if isinstance(data, dict):
            for k, v in list(data.items()):
                if k in cls.preserve_case:
                    continue
                lk = k[0].lower() + k[1:]
                data[lk] = data.pop(k)
                # describe doesn't return empty list/dict by default
                if isinstance(v, (list, dict)) and not v and lk not in cls.preserve_empty:
                    data.pop(lk)
                elif isinstance(v, (dict, list)):
                    data[lk] = cls.lower_keys(v)
        elif isinstance(data, list):
            return list(map(cls.lower_keys, data))
        return data

    def load_resource(self, item):
        resource = self.lower_keys(super().load_resource(item))
        if self.mapped_keys:
            return self.remap_keys(resource)
        return resource


class ClusterDescribe(query.DescribeSource):

    def augment(self, resources):
        resources = super(ClusterDescribe, self).augment(resources)
        ecs_tag_normalize(resources)
        return resources


@resources.register('ecs')
class ECSCluster(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ecs'
        enum_spec = ('list_clusters', 'clusterArns', None)
        batch_detail_spec = (
            'describe_clusters', 'clusters', None, 'clusters', {
                'include': ['TAGS', 'SETTINGS', 'CONFIGURATIONS']
            })
        name = "clusterName"
        arn = id = "clusterArn"
        arn_type = 'cluster'
        config_type = cfn_type = 'AWS::ECS::Cluster'

    source_mapping = {
        'describe': ClusterDescribe,
        'config': query.ConfigSource
    }


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


class ECSServiceConfigSource(ContainerConfigSource):
    perserve_empty = {
        'placementConstraints', 'placementStrategy',
        'serviceRegistries', 'Tags', 'loadBalancers'}

    mapped_keys = {
        'role': 'roleArn', 'cluster': 'clusterArn'}


@resources.register('ecs-service')
class Service(query.ChildResourceManager):

    chunk_size = 10

    class resource_type(query.TypeInfo):
        service = 'ecs'
        name = 'serviceName'
        arn = id = 'serviceArn'
        enum_spec = ('list_services', 'serviceArns', None)
        parent_spec = ('ecs', 'cluster', None)
        supports_trailevents = True
        config_type = cfn_type = 'AWS::ECS::Service'

    source_mapping = {
        'config': ECSServiceConfigSource,
        'describe-child': ECSServiceDescribeSource,
        'describe': ECSServiceDescribeSource,
    }

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
    schema_alias = False
    permissions = ('ecs:DescribeTaskDefinition',
                   'ecs:ListTaskDefinitions')
    related_key = 'taskDefinition'

    def process(self, resources, event=None):
        self.task_defs = {t['taskDefinitionArn']: t for t in self.get_task_defs(resources)}
        return super(RelatedTaskDefinitionFilter, self).process(resources)

    def get_task_defs(self, resources):
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
        return task_defs

    def __call__(self, i):
        task = self.task_defs[i[self.related_key]]
        return self.match(task)


@Service.filter_registry.register('task-definition')
class ServiceTaskDefinitionFilter(RelatedTaskDefinitionFilter):
    """Filter services by their task definitions.

    :Example:

     Find any fargate services that are running with a particular
     image in the task and stop them.

    .. code-block:: yaml

       policies:
         - name: fargate-find-stop-image
           resource: ecs-task
           filters:
             - launchType: FARGATE
             - type: task-definition
               key: "containerDefinitions[].image"
               value: "elasticsearch/elasticsearch:6.4.3"
               value_type: swap
               op: contains
           actions:
             - type: stop
    """


@ECSCluster.filter_registry.register('ebs-storage')
class Storage(ValueFilter):
    """Filter clusters by configured EBS storage parameters.

    :Example:

    Find any ECS clusters that have instances that are using unencrypted EBS volumes.

    .. code-block:: yaml

        policies:
          - name: encrypted-ebs-volumes
            resource: ecs
            filters:
              - type: ebs-storage
                key: Encrypted
                value: true
    """

    schema = type_schema(
        'ebs-storage', rinherit=ValueFilter.schema,
        operator={'type': 'string', 'enum': ['or', 'and']},
    )
    schema_alias = False

    def get_permissions(self):
        return (self.manager.get_resource_manager('ebs').get_permissions() +
                self.manager.get_resource_manager('ec2').get_permissions() +
                self.manager.get_resource_manager('ecs').get_permissions()
                )

    def process(self, resources, event=None):
        self.storage = self.get_storage(resources)
        self.skip = []
        self.operator = self.data.get(
            'operator', 'or') == 'or' and any or all
        return list(filter(self, resources))

    def get_storage(self, resources):
        manager = self.manager.get_resource_manager('ecs-container-instance')

        storage = {}
        for cluster_set in utils.chunks(resources, 200):
            for cluster in cluster_set:
                cluster["clusterArn"]
                instances = manager.resources({
                    "cluster": cluster['clusterArn'],
                }, augment=False)
                instances = manager.get_resources(instances, augment=False)
                storage[cluster["clusterArn"]] = []

                for instance in instances:
                    storage[cluster["clusterArn"]].extend(self.get_ebs_volumes([instance["ec2InstanceId"]]))

        return storage

    def get_ebs_volumes(self, resources):
        volumes = []
        ec2_manager = self.manager.get_resource_manager('ec2')
        ebs_manager = self.manager.get_resource_manager('ebs')
        for instance_set in utils.chunks(resources, 200):
            instance_set = ec2_manager.get_resources(instance_set)
            volume_ids = []
            for i in instance_set:
                for bd in i.get('BlockDeviceMappings', ()):
                    if 'Ebs' not in bd:
                        continue
                    volume_ids.append(bd['Ebs']['VolumeId'])
            for v in ebs_manager.get_resources(volume_ids):
                if not v['Attachments']:
                    continue
                volumes.append(v)
        return volumes

    def __call__(self, i):
        storage = self.storage.get(i["clusterArn"])

        if not storage:
            return False
        return self.operator(map(self.match, storage))


@Service.filter_registry.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = ""
    expressions = ('taskSets[].networkConfiguration.awsvpcConfiguration.subnets[]',
                'deployments[].networkConfiguration.awsvpcConfiguration.subnets[]',
                'networkConfiguration.awsvpcConfiguration.subnets[]')

    def get_related_ids(self, resources):
        subnet_ids = set()
        for exp in self.expressions:
            cexp = jmespath_compile(exp)
            for r in resources:
                ids = cexp.search(r)
                if ids:
                    subnet_ids.update(ids)
        return list(subnet_ids)


@Service.filter_registry.register('security-group')
class SGFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = ""
    expressions = ('taskSets[].networkConfiguration.awsvpcConfiguration.securityGroups[]',
                'deployments[].networkConfiguration.awsvpcConfiguration.securityGroups[]',
                'networkConfiguration.awsvpcConfiguration.securityGroups[]')

    def get_related_ids(self, resources):
        sg_ids = set()
        for exp in self.expressions:
            cexp = jmespath_compile(exp)
            for r in resources:
                ids = cexp.search(r)
                if ids:
                    sg_ids.update(ids)
        return list(sg_ids)


@Service.filter_registry.register('network-location', net_filters.NetworkLocation)
@Service.action_registry.register('modify-definition')
class UpdateTemplate(BaseAction):

    schema = type_schema(
        'modify-definition',
        properties={'type': 'object'},
    )

    permissions = ("ecs:RegisterTaskDefinition", "ecs:UpdateService")

    def validate(self):
        if self.data.get('properties'):
            return
        found = False
        for f in self.manager.iter_filters():
            if isinstance(f, CostHubRecommendation):
                found = True
        if not found:
            raise PolicyValidationError(
                "modify-definition: either properties specified or am optimization filter used"
            )

    def process(self, resources):
        task_def_filter = ServiceTaskDefinitionFilter({}, self.manager)
        task_defs = {t['taskDefinitionArn']: t for t in task_def_filter.get_task_defs(resources)}
        client = local_session(self.manager.session_factory).client('ecs')

        # we can only modify task definition when ecs is controlling the deployment.
        resources = self.filter_resources(resources, "deploymentController.type", ("ECS",))

        nack = 0
        for r in resources:
            r_task_def = task_defs[r[task_def_filter.related_key]]
            m_task_def = self.get_target_task_def(r, r_task_def)
            if m_task_def is None:
                nack += 1
                continue
            response = client.register_task_definition(**m_task_def)
            task_arn = response['taskDefinition']['taskDefinitionArn']
            cluster, _ = Arn.parse(r['serviceArn']).resource.split('/', 1)
            client.update_service(
                cluster=cluster,
                service=r['serviceName'],
                taskDefinition=task_arn
            )
        if nack:
            self.log.warning("modify-definition %d services not modified", nack)

    task_def_normalized = [
        "taskDefinitionArn", "revision", "status",
        "registeredAt", "registeredBy", "requiresAttributes",
    ]

    task_def_remap = {
        "compatibilities": "requiresCompatibilities",
    }

    def get_target_task_def(self, resource, current_task_def):
        target_task_def = copy.deepcopy(current_task_def)
        target_task_def.update(self.data.get('properties', {}))
        cost_optimization = resource.get(CostHubRecommendation.annotation_key)

        if cost_optimization and cost_optimization['actionType'] == 'Rightsize':
            cpu, mem = cost_optimization["recommendedResourceSummary"].split("/")
            cpu = int(float(cpu.split(" ")[0]))
            mem = int(mem.split(" ")[0])
            target_task_def["cpu"] = str(cpu)
            target_task_def["memory"] = str(mem)
            target_task_def = self.update_target_containers_size(current_task_def, target_task_def)

        if target_task_def == current_task_def or target_task_def is None:
            return

        # normalize from describe to register formats
        for k in self.task_def_normalized:
            target_task_def.pop(k, None)
        for ck, dk in self.task_def_remap.items():
            if ck in target_task_def:
                target_task_def[dk] = target_task_def.pop(ck)
        tags = []
        for t in target_task_def.pop('Tags', []):
            tags.append({'key': t['Key'], 'value': t['Value']})
        if tags:
            target_task_def['tags'] = tags
        return target_task_def

    def update_target_containers_size(self, current_task_def, target_task_def):
        """Update container memory/size targets.

        We need to update memory/cpu requirements of the containers within
        the task, so the total of the containers in the task def
        matches the definition.

        for a task w/ a single container this is simple, make the container match
        the definition.

        for a multi container task, we need select a heuristic
        (proportional, largest) with some notion of a floor / min for
        proportional. for now we punt on multi-container tasks.
        """
        if len(target_task_def['containerDefinitions']) > 1:
            return
        container_def = target_task_def['containerDefinitions'][0]
        container_def['memory'] = int(target_task_def['memory'])
        container_def['cpu'] = int(target_task_def['cpu'])
        return target_task_def


@Service.action_registry.register('modify')
class UpdateService(BaseAction):
    """Action to update service

    :example:

    .. code-block:: yaml

            policies:
              - name: no-public-ips-services
                resource: ecs-service
                filters:
                  - 'networkConfiguration.awsvpcConfiguration.assignPublicIp': 'ENABLED'
                actions:
                  - type: modify
                    update:
                      networkConfiguration:
                        awsvpcConfiguration:
                          assignPublicIp: DISABLED
    """

    schema = type_schema('modify',
        update={
            'desiredCount': {'type': 'integer'},
            'taskDefinition': {'type': 'string'},
            'deploymentConfiguration': {
                'type': 'object',
                'properties': {
                    'maximumPercent': {'type': 'integer'},
                    'minimumHealthyPercent': {'type': 'integer'},
                }
            },
            'networkConfiguration': {
                'type': 'object',
                'properties': {
                    'awsvpcConfiguration': {
                        'type': 'object',
                        'properties': {
                            'subnets': {
                                'type': 'array',
                                'items': {
                                    'type': 'string',
                                },
                                'minItems': 1
                            },
                            'securityGroups': {
                                'items': {
                                    'type': 'string',
                                },
                            },
                            'assignPublicIp': {
                                'type': 'string',
                                'enum': ['ENABLED', 'DISABLED'],
                            }
                        }
                    }
                }
            },
            'platformVersion': {'type': 'string'},
            'forceNewDeployment': {'type': 'boolean', 'default': False},
            'healthCheckGracePeriodSeconds': {'type': 'integer'},
        }
    )

    permissions = ('ecs:UpdateService',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ecs')
        update = self.data.get('update')

        for r in resources:
            param = {}

            # Handle network separately as it requires atomic updating, and populating
            # defaults from the resource.
            net_update = update.get('networkConfiguration', {}).get('awsvpcConfiguration')
            if net_update:
                net_param = dict(r['networkConfiguration']['awsvpcConfiguration'])
                param['networkConfiguration'] = {'awsvpcConfiguration': net_param}
                for k, v in net_update.items():
                    net_param[k] = v

            for k, v in update.items():
                if k == 'networkConfiguration':
                    continue
                elif r.get(k) != v:
                    param[k] = v

            if not param:
                continue

            client.update_service(
                cluster=r['clusterArn'], service=r['serviceName'], **param)


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
                desiredCount = 0

                # Two different types of responses:
                # Deployments would appear for normal services
                # TaskSets would show for Blue/Green deployment
                if 'deployments' in r:
                    primary = [d for d in r['deployments'] if d['status'] == 'PRIMARY'].pop()
                    desiredCount = primary.get('desiredCount', 0)
                elif 'taskSets' in r:
                    primary = [t for t in r['taskSets'] if t['status'] == 'PRIMARY'].pop()
                    desiredCount = primary.get('computedDesiredCount', 0)

                if desiredCount > 0:
                    retry(client.update_service,
                          cluster=r['clusterArn'], service=r['serviceName'], desiredCount=0)

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

    class resource_type(query.TypeInfo):
        service = 'ecs'
        arn = id = name = 'taskArn'
        arn_type = 'task'
        enum_spec = ('list_tasks', 'taskArns', None)
        parent_spec = ('ecs', 'cluster', None)
        supports_trailevents = True
        cfn_type = 'AWS::ECS::TaskSet'

    @property
    def source_type(self):
        source = self.data.get('source', 'describe')
        if source in ('describe', 'describe-child'):
            source = 'describe-ecs-task'
        return source

    def get_resources(self, ids, cache=True, augment=True):
        return super(Task, self).get_resources(ids, cache, augment=False)


@Task.filter_registry.register('subnet')
class TaskSubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "attachments[].details[?name == 'subnetId'].value[]"


@Task.filter_registry.register('security-group')
class TaskSGFilter(net_filters.SecurityGroupFilter):

    ecs_group_cache = None

    RelatedIdsExpression = ""
    eni_expression = "attachments[].details[?name == 'networkInterfaceId'].value[]"
    sg_expression = "Groups[].GroupId[]"

    def _get_related_ids(self, resources):
        groups = dict()
        eni_ids = set()

        cexp = jmespath_compile(self.eni_expression)
        for r in resources:
            ids = cexp.search(r)
            if ids:
                eni_ids.update(ids)

        if eni_ids:
            client = local_session(self.manager.session_factory).client('ec2')
            response = client.describe_network_interfaces(
                NetworkInterfaceIds=list(eni_ids)
            )
            if response["NetworkInterfaces"]:
                cexp = jmespath_compile(self.sg_expression)
                for r in response["NetworkInterfaces"]:
                    ids = cexp.search(r)
                    if ids:
                        groups[r["NetworkInterfaceId"]] = ids
                        self.ecs_group_cache = groups

        return groups

    def get_related_ids(self, resources):
        if not self.ecs_group_cache:
            self.ecs_group_cache = self._get_related_ids(resources)

        group_ids = set()
        cexp = jmespath_compile(self.eni_expression)
        for r in resources:
            ids = cexp.search(r)
            for group_id in ids:
                group_ids.update(self.ecs_group_cache.get(group_id, ()))
        return list(group_ids)


@Task.filter_registry.register('network-location', net_filters.NetworkLocation)
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
             - type: stop

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


class DescribeTaskDefinition(DescribeSource):

    def get_resources(self, ids, cache=True):
        if cache:
            resources = self.manager._get_cached_resources(ids)
            if resources is not None:
                return resources
        try:
            resources = self.augment(ids)
            return resources
        except ClientError as e:
            self.manager.log.warning("event ids not resolved: %s error:%s" % (ids, e))
            return []

    def augment(self, resources):
        results = []
        client = local_session(self.manager.session_factory).client('ecs')
        for task_def_set in resources:
            response = self.manager.retry(
                client.describe_task_definition,
                taskDefinition=task_def_set,
                include=['TAGS'])
            r = response['taskDefinition']
            r['tags'] = response.get('tags', [])
            results.append(r)
        ecs_tag_normalize(results)
        return results


class ConfigECSTaskDefinition(ContainerConfigSource):

    preserve_empty = {'mountPoints', 'portMappings', 'volumesFrom'}


@resources.register('ecs-task-definition')
class TaskDefinition(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ecs'
        arn = id = name = 'taskDefinitionArn'
        enum_spec = ('list_task_definitions', 'taskDefinitionArns', None)
        cfn_type = config_type = 'AWS::ECS::TaskDefinition'
        arn_type = 'task-definition'

    source_mapping = {
        'config': ConfigECSTaskDefinition,
        'describe': DescribeTaskDefinition
    }

    def get_resources(self, ids, cache=True, augment=True):
        return super(TaskDefinition, self).get_resources(ids, cache, augment=False)


@TaskDefinition.action_registry.register('delete')
class DeleteTaskDefinition(BaseAction):
    """Delete/DeRegister a task definition.

    The definition will be marked as InActive. Currently running
    services and task can still reference, new services & tasks
    can't.

    force is False by default. When given as True, the task definition will
    be permanently deleted.

    .. code-block:: yaml

       policies:
         - name: deregister-task-definition
           resource: ecs-task-definition
           filters:
             - family: test-task-def
           actions:
             - type: delete

         - name: delete-task-definition
           resource: ecs-task-definition
           filters:
             - family: test-task-def
           actions:
             - type: delete
               force: True
    """

    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = ('ecs:DeregisterTaskDefinition', 'ecs:DeleteTaskDefinitions',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ecs')
        retry = get_retry(('Throttling',))
        force = self.data.get('force', False)

        for r in resources:
            if r['status'] == 'INACTIVE':
                continue
            try:
                retry(client.deregister_task_definition,
                      taskDefinition=r['taskDefinitionArn'])
            except ClientError as e:
                if e.response['Error'][
                    'Message'] != 'The specified task definition does not exist.':
                    raise

        if force:
            task_definitions_arns = [
                r['taskDefinitionArn']
                for r in resources
            ]
            for chunk in chunks(task_definitions_arns, size=10):
                retry(client.delete_task_definitions, taskDefinitions=chunk)


@resources.register('ecs-container-instance')
class ContainerInstance(query.ChildResourceManager):

    chunk_size = 100

    class resource_type(query.TypeInfo):
        service = 'ecs'
        id = name = 'containerInstanceArn'
        enum_spec = ('list_container_instances', 'containerInstanceArns', None)
        parent_spec = ('ecs', 'cluster', None)
        arn = "containerInstanceArn"

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
                containerInstances=service_set).get('containerInstances', [])
            # Many Container Instance API calls require the cluster_id, adding as a
            # custodian specific key in the resource
            for i in r:
                i['c7n:cluster'] = cluster_id
            results.extend(r)
        ecs_tag_normalize(results)
        return results


@ContainerInstance.filter_registry.register('subnet')
class ContainerInstanceSubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "attributes[?name == 'ecs.subnet-id'].value[]"


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


@ECSCluster.action_registry.register('tag')
@TaskDefinition.action_registry.register('tag')
@Service.action_registry.register('tag')
@Task.action_registry.register('tag')
@ContainerInstance.action_registry.register('tag')
class TagEcsResource(Tag):
    """Action to create tag(s) on an ECS resource
    (ecs, ecs-task-definition, ecs-service, ecs-task, ecs-container-instance)

    Requires arns in new format for tasks, services, and container-instances.
    https://docs.aws.amazon.com/AmazonECS/latest/userguide/ecs-resource-ids.html

    :example:

    .. code-block:: yaml

            policies:
              - name: tag-ecs-service
                resource: ecs-service
                filters:
                  - "tag:target-tag": absent
                  - type: taggable
                    state: true
                actions:
                  - type: tag
                    key: target-tag
                    value: target-value
    """
    permissions = ('ecs:TagResource',)
    batch_size = 1

    def process_resource_set(self, client, resources, tags):
        mid = self.manager.resource_type.id
        tags = [{'key': t['Key'], 'value': t['Value']} for t in tags]
        old_arns = 0
        for r in resources:
            if not ecs_taggable(self.manager.resource_type, r):
                old_arns += 1
                continue
            client.tag_resource(resourceArn=r[mid], tags=tags)
        if old_arns:
            self.log.warn("Couldn't tag %d resource(s). Needs new ARN format", old_arns)


@ECSCluster.action_registry.register('remove-tag')
@TaskDefinition.action_registry.register('remove-tag')
@Service.action_registry.register('remove-tag')
@Task.action_registry.register('remove-tag')
@ContainerInstance.action_registry.register('remove-tag')
class RemoveTagEcsResource(RemoveTag):
    """Remove tag(s) from ECS resources
    (ecs, ecs-task-definition, ecs-service, ecs-task, ecs-container-instance)

    :example:

    .. code-block:: yaml

            policies:
              - name: ecs-service-remove-tag
                resource: ecs-service
                filters:
                  - type: taggable
                    state: true
                actions:
                  - type: remove-tag
                    tags: ["BadTag"]
    """
    permissions = ('ecs:UntagResource',)
    batch_size = 1

    def process_resource_set(self, client, resources, keys):
        old_arns = 0
        for r in resources:
            if not ecs_taggable(self.manager.resource_type, r):
                old_arns += 1
                continue
            client.untag_resource(resourceArn=r[self.id_key], tagKeys=keys)
        if old_arns != 0:
            self.log.warn("Couldn't untag %d resource(s). Needs new ARN format", old_arns)


@ECSCluster.action_registry.register('mark-for-op')
@TaskDefinition.action_registry.register('mark-for-op')
@Service.action_registry.register('mark-for-op')
@Task.action_registry.register('mark-for-op')
@ContainerInstance.action_registry.register('mark-for-op')
class MarkEcsResourceForOp(TagDelayedAction):
    """Mark ECS resources for deferred action
    (ecs, ecs-task-definition, ecs-service, ecs-task, ecs-container-instance)

    Requires arns in new format for tasks, services, and container-instances.
    https://docs.aws.amazon.com/AmazonECS/latest/userguide/ecs-resource-ids.html

    :example:

    .. code-block:: yaml

        policies:
          - name: ecs-service-invalid-tag-stop
            resource: ecs-service
            filters:
              - "tag:InvalidTag": present
              - type: taggable
                state: true
            actions:
              - type: mark-for-op
                op: delete
                days: 1
    """


@Service.filter_registry.register('taggable')
@Task.filter_registry.register('taggable')
@ContainerInstance.filter_registry.register('taggable')
class ECSTaggable(Filter):
    """
    Filter ECS resources on arn-format
    https://docs.aws.amazon.com/AmazonECS/latest/userguide/ecs-resource-ids.html
    :example:

        .. code-block:: yaml

            policies:
                - name: taggable
                  resource: ecs-service
                  filters:
                    - type: taggable
                      state: True
    """

    schema = type_schema('taggable', state={'type': 'boolean'})

    def get_permissions(self):
        return self.manager.get_permissions()

    def process(self, resources, event=None):
        if not self.data.get('state'):
            return [r for r in resources if not ecs_taggable(self.manager.resource_type, r)]
        else:
            return [r for r in resources if ecs_taggable(self.manager.resource_type, r)]


ECSCluster.filter_registry.register('marked-for-op', TagActionFilter)
TaskDefinition.filter_registry.register('marked-for-op', TagActionFilter)
Service.filter_registry.register('marked-for-op', TagActionFilter)
Task.filter_registry.register('marked-for-op', TagActionFilter)
ContainerInstance.filter_registry.register('marked-for-op', TagActionFilter)

ECSCluster.action_registry.register('auto-tag-user', AutoTagUser)
TaskDefinition.action_registry.register('auto-tag-user', AutoTagUser)
Service.action_registry.register('auto-tag-user', AutoTagUser)
Task.action_registry.register('auto-tag-user', AutoTagUser)
ContainerInstance.action_registry.register('auto-tag-user', AutoTagUser)

Service.filter_registry.register('offhour', OffHour)
Service.filter_registry.register('onhour', OnHour)


@Service.action_registry.register('resize')
class AutoscalingECSService(AutoscalingBase):
    permissions = (
        'ecs:UpdateService',
        'ecs:TagResource',
        'ecs:UntagResource',
    )

    service_namespace = 'ecs'
    scalable_dimension = 'ecs:service:DesiredCount'

    def get_resource_id(self, resource):
        return resource['serviceArn'].split(':')[-1]

    def get_resource_tag(self, resource, key):
        if 'Tags' in resource:
            for tag in resource['Tags']:
                if tag['Key'] == key:
                    return tag['Value']
        return None

    def get_resource_desired(self, resource):
        return int(resource['desiredCount'])

    def set_resource_desired(self, resource, desired):
        client = local_session(self.manager.session_factory).client('ecs')
        client.update_service(
            cluster=resource['clusterArn'],
            service=resource['serviceName'],
            desiredCount=desired,
        )
