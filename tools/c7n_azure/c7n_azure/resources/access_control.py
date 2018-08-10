# Copyright 2018 Capital One Services, LLC
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

import logging

from azure.graphrbac import GraphRbacManagementClient
from azure.graphrbac.models import GetObjectsParameters
from c7n_azure.provider import Azure
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager, DescribeSource
from c7n_azure.session import Session
from msrestazure.azure_exceptions import CloudError

from c7n.actions import BaseAction
from c7n.config import Config
from c7n.ctx import ExecutionContext
from c7n.filters import FilterValidationError
from c7n.filters import ValueFilter
from c7n.filters.related import RelatedResourceFilter
from c7n.query import sources
from c7n.utils import local_session
from c7n.utils import type_schema

log = logging.getLogger('custodian.azure.access_control')


@resources.register('roleassignment')
class RoleAssignment(QueryResourceManager):

    class resource_type(object):
        service = 'azure.mgmt.authorization'
        client = 'AuthorizationManagementClient'
        enum_spec = ('role_assignments', 'list', None)
        get_spec = ('role_assignments', 'get_by_id', None)
        id = 'id'
        default_report_fields = (
            'principalName',
            'displayName',
            'aadType',
            'name',
            'type',
            'properties.scope',
            'properties.roleDefinitionId'
        )

    def augment(self, resources):
        s = Session(resource='https://graph.windows.net')
        graph_client = GraphRbacManagementClient(s.get_credentials(), s.get_tenant_id())

        object_ids = list(set(
            resource['properties']['principalId'] for resource in resources
            if resource['properties']['principalId']))

        object_params = GetObjectsParameters(
            include_directory_object_references=True,
            object_ids=object_ids)

        aad_objects = graph_client.objects.get_objects_by_object_ids(object_params)

        try:
            principal_dics = {aad_object.object_id: aad_object for aad_object in aad_objects}

            for resource in resources:
                if resource['properties']['principalId'] in principal_dics.keys():
                    graph_resource = principal_dics[resource['properties']['principalId']]
                    resource['principalName'] = self.get_principal_name(graph_resource)
                    resource['displayName'] = graph_resource.display_name
                    resource['aadType'] = graph_resource.object_type

        except CloudError:
            log.warning('Credentials not authorized for access to read from Microsoft Graph. \n '
                        'Can not query on principalName, displayName, or aadType. \n'
                        )

        return resources

    @staticmethod
    def get_principal_name(graph_object):
        if graph_object.user_principal_name:
            return graph_object.user_principal_name
        elif graph_object.service_principal_names:
            return graph_object.service_principal_names[0]
        return graph_object.display_name or ''


@resources.register('roledefinition')
class RoleDefinition(QueryResourceManager):

    class resource_type(object):
        service = 'azure.mgmt.authorization'
        client = 'AuthorizationManagementClient'
        get_spec = ('role_definitions', 'get_by_id', None)
        type = 'roleDefinition'
        id = 'id'
        default_report_fields = (
            'properties.roleName',
            'properties.description',
            'id',
            'name',
            'type'
            'properties.type',
            'properties.permissions'
        )

    @property
    def source_type(self):
        return self.data.get('source', 'describe-azure-roledefinition')


@sources.register('describe-azure-roledefinition')
class DescribeSource(DescribeSource):

    def get_resources(self, query):
        s = local_session(self.manager.session_factory)
        client = s.client('azure.mgmt.authorization.AuthorizationManagementClient')
        scope = '/subscriptions/%s' % (s.subscription_id)
        resources = client.role_definitions.list(scope)
        return [r.serialize(True) for r in resources]


@RoleAssignment.filter_registry.register('role')
class RoleFilter(RelatedResourceFilter):
    """Filters role assignments based on role definitions

    :Example:

        .. code-block:: yaml

            policies:
               - name: assignments-by-role-definition
                 resource: azure.roleassignment
                 filters:
                    - type: role
                      key: properties.roleName
                      op: in
                      value: Owner
    """

    schema = type_schema('role', rinherit=ValueFilter.schema)

    RelatedResource = "c7n_azure.resources.access_control.RoleDefinition"
    RelatedIdsExpression = "properties.roleDefinitionId"


@RoleAssignment.filter_registry.register('resource-access')
class ResourceAccessFilter(RelatedResourceFilter):
    """Filters role assignments that have access to a certain
    type of azure resource.

    :Example:

        .. code-block:: yaml

            policies:
               - name: assignments-by-azure-resource
                 resource: azure.roleassignment
                 filters:
                    - type: resource-access
                      relatedResource: azure.vm
    """

    schema = type_schema(
        'resource-access',
        relatedResource={'type': 'string'},
        rinherit=RelatedResourceFilter.schema,
        required=['relatedResource']
    )

    def __init__(self, data, manager=None):
        super(ResourceAccessFilter, self).__init__(data, manager)
        resource_type = self.data['relatedResource']
        self.factory = Azure.resources.get(
            resource_type.rsplit('.', 1)[-1])

    def get_related(self, resources):
        ctx = ExecutionContext(local_session(Session), self.data, Config.empty())
        manager = self.factory(ctx, self.data)
        related = manager.source.get_resources(None)
        if self.data.get('op'):
            return [r['id'] for r in related if self.match(r)]
        else:
            return [r['id'] for r in related]

    def process_resource(self, resource, related):
        for r in related:
            if resource['properties']['scope'] in r:
                return True

        return False

    def validate(self):
        if self.factory is None:
            raise FilterValidationError(
                "The related resource is not a custodian supported azure resource"
            )
        if (self.data['relatedResource'] == 'azure.roleassignment' or
                self.data['relatedResource'] == 'azure.roledefinition'):
            raise FilterValidationError(
                "The related resource can not be role assignments or role definitions"
            )


@RoleAssignment.action_registry.register('delete')
class DeleteAssignmentAction(BaseAction):

    schema = type_schema('delete')

    def __init__(self, data=None, manager=None, log_dir=None):
        super(DeleteAssignmentAction, self).__init__(data, manager, log_dir)
        self.client = self.manager.get_client()

    def delete(self, assignment_scope, assignment_name):
        self.client.role_assignments.delete(assignment_scope, assignment_name)

    def process(self, assignments):
        for assignment in assignments:
            self.delete(assignment['properties']['scope'], assignment['name'])
