# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo

from c7n.utils import local_session, type_schema


@resources.register('batch-compute')
class ComputeEnvironment(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'batch'
        filter_name = 'computeEnvironments'
        filter_type = 'list'
        id = name = "computeEnvironmentName"
        arn = "computeEnvironmentArn"
        arn_type = "compute-environment"
        enum_spec = (
            'describe_compute_environments', 'computeEnvironments', None)
        cfn_type = config_type = 'AWS::Batch::ComputeEnvironment'


@ComputeEnvironment.filter_registry.register('security-group')
class ComputeSGFilter(SecurityGroupFilter):

    RelatedIdsExpression = "computeResources.securityGroupIds[]"


@ComputeEnvironment.filter_registry.register('subnet')
class ComputeSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "computeResources.subnets[]"


@resources.register('batch-definition')
class JobDefinition(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'batch'
        filter_name = 'jobDefinitions'
        filter_type = 'list'
        arn = "jobDefinitionArn"
        arn_type = 'job-definition'
        id = name = "jobDefinitionName"
        enum_spec = (
            'describe_job_definitions', 'jobDefinitions', None)
        cfn_type = 'AWS::Batch::JobDefinition'


@ComputeEnvironment.action_registry.register('update-environment')
class UpdateComputeEnvironment(BaseAction):
    """Updates an AWS batch compute environment

    :example:

    .. code-block:: yaml

        policies:
          - name: update-environments
            resource: batch-compute
            filters:
              - computeResources.desiredvCpus: 0
              - state: ENABLED
            actions:
              - type: update-environment
                state: DISABLED
    """
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['update-environment']},
            'computeEnvironment': {'type': 'string'},
            'state': {'type': 'string', 'enum': ['ENABLED', 'DISABLED']},
            'computeResources': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'minvCpus': {'type': 'integer'},
                    'maxvCpus': {'type': 'integer'},
                    'desiredvCpus': {'type': 'integer'}
                }
            },
            'serviceRole': {'type': 'string'}
        }
    }
    permissions = ('batch:UpdateComputeEnvironment',)
    valid_origin_status = ('VALID', 'INVALID')

    def process(self, resources):
        resources = self.filter_resources(resources, 'status', self.valid_origin_status)
        client = local_session(self.manager.session_factory).client('batch')
        params = dict(self.data)
        params.pop('type')
        for r in resources:
            params['computeEnvironment'] = r['computeEnvironmentName']
            client.update_compute_environment(**params)


@ComputeEnvironment.action_registry.register('delete')
class DeleteComputeEnvironment(BaseAction):
    """Delete an AWS batch compute environment

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-environments
            resource: batch-compute
            filters:
              - computeResources.desiredvCpus: 0
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    permissions = ('batch:DeleteComputeEnvironment',)
    valid_origin_states = ('DISABLED',)
    valid_origin_status = ('VALID', 'INVALID')

    def delete_environment(self, client, r):
        client.delete_compute_environment(
            computeEnvironment=r['computeEnvironmentName'])

    def process(self, resources):
        resources = self.filter_resources(
            self.filter_resources(
                resources, 'state', self.valid_origin_states),
            'status', self.valid_origin_status)
        client = local_session(self.manager.session_factory).client('batch')
        for e in resources:
            self.delete_environment(client, e)


@JobDefinition.action_registry.register('deregister')
class DefinitionDeregister(BaseAction):
    """Deregisters a batch definition

    :example:

    .. code-block:: yaml

        policies:
          - name: deregister-definition
            resource: batch-definition
            filters:
              - containerProperties.image: amazonlinux
            actions:
              - type: deregister
    """
    schema = type_schema('deregister')
    permissions = ('batch:DeregisterJobDefinition',)
    valid_origin_states = ('ACTIVE',)

    def deregister_definition(self, r):
        self.client.deregister_job_definition(
            jobDefinition='%s:%s' % (r['jobDefinitionName'],
                                     r['revision']))

    def process(self, resources):
        resources = self.filter_resources(resources, 'status', self.valid_origin_states)
        self.client = local_session(
            self.manager.session_factory).client('batch')
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.deregister_definition, resources))


@resources.register('batch-queue')
class BatchJobQueue(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'batch'
        filter_name = 'jobQueues'
        filter_type = 'list'
        id = name = 'jobQueueName'
        arn = 'jobQueueArn'
        arn_type = 'job-queue'
        enum_spec = (
            'describe_job_queues', 'jobQueues', None)
        cfn_type = config_type = 'AWS::Batch::JobQueue'
