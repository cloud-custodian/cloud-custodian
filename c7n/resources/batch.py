# Copyright 2017-2018 Capital One Services, LLC
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

from c7n.actions import BaseAction
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager

from c7n.utils import local_session, type_schema


@resources.register('batch-compute')
class ComputeEnvironment(QueryResourceManager):

    class resource_type(object):
        service = 'batch'
        filter_name = 'computeEnvironments'
        filter_type = 'list'
        dimension = None
        id = name = "computeEnvironmentName"
        enum_spec = (
            'describe_compute_environments', 'computeEnvironments', None)


@ComputeEnvironment.filter_registry.register('security-group')
class ComputeSGFilter(SecurityGroupFilter):

    RelatedIdsExpression = "computeResources.securityGroupIds"


@ComputeEnvironment.filter_registry.register('subnet')
class ComputeSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "computeResources.subnets"


@resources.register('batch-definition')
class JobDefinition(QueryResourceManager):

    class resource_type(object):
        service = 'batch'
        filter_name = 'jobDefinitions'
        filter_type = 'list'
        dimension = None
        id = name = "jobDefinitionName"
        enum_spec = (
            'describe_job_definitions', 'jobDefinitions', None)


class StateTransitionFilter(object):
    """Filter resources by state.

    Try to simplify construction for policy authors by automatically
    filtering elements (filters or actions) to the resource states
    they are valid for.
    """
    valid_origin_states = ()

    def filter_resource_state(self, resources, key, states=None):
        states = states or self.valid_origin_states
        if not states:
            return resources
        orig_length = len(resources)
        results = [r for r in resources if r[key] in states]
        if orig_length != len(results):
            self.log.warn(
                "%s implicitly filtered %d of %d resources with valid %s" % (
                    self.__class__.__name__,
                    len(results), orig_length, key.lower()))
        return results


@ComputeEnvironment.action_registry.register('update-environment')
class UpdateComputeEnvironment(BaseAction, StateTransitionFilter):
    """Updates an AWS batch compute environment

    :example:

    .. code-block: yaml

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
        resources = self.filter_resource_state(
            resources, 'status', self.valid_origin_status)
        client = local_session(self.manager.session_factory).client('batch')
        params = dict(self.data)
        params.pop('type')
        for r in resources:
            params['computeEnvironment'] = r['computeEnvironmentName']
            client.update_compute_environment(**params)


@ComputeEnvironment.action_registry.register('delete')
class DeleteComputeEnvironment(BaseAction, StateTransitionFilter):
    """Delete an AWS batch compute environment

    :example:

    .. code-block: yaml

        policies:
          - name: delete-environments
            resource: batch-compute
            filters:
              - computeResources.desiredvCpus: 0
            action:
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
        resources = self.filter_resource_state(
            self.filter_resource_state(
                resources, 'state', self.valid_origin_states),
            'status', self.valid_origin_status)
        client = local_session(self.manager.session_factory).client('batch')
        for e in resources:
            self.delete_environment(client, e)


@JobDefinition.action_registry.register('deregister')
class DefinitionDeregister(BaseAction, StateTransitionFilter):
    """Deregisters a batch definition

    :example:

    .. code-block: yaml

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
        resources = self.filter_resource_state(
            resources, 'status', self.valid_origin_states)
        self.client = local_session(
            self.manager.session_factory).client('batch')
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.deregister_definition, resources))
