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
import re

import six
from azure.graphrbac import GraphRbacManagementClient
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import Azure
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager, DescribeSource
from c7n_azure.session import Session
from c7n_azure.utils import GraphHelper

from c7n.filters import Filter
from c7n.filters import FilterValidationError
from c7n.filters import ValueFilter
from c7n.filters.related import RelatedResourceFilter
from c7n.query import sources
from c7n.utils import local_session
from c7n.utils import type_schema

log = logging.getLogger('custodian.azure.access_control')


@resources.register('roleassignment')
class RoleAssignment(QueryResourceManager):
    """Role assignments map role definitions to principals. The Azure
    object only contains the unique ID of the principal, however we
    attempt to augment the object with the prinicpal name, display name
    and type from AAD.

    Augmenting with data from AAD requires executing account to have
    permissions to read from the Microsoft AAD Graph. For Service Principal
    Authorization the Service Principal must have the permissions to
    `read all users' full profiles`. Azure CLI authentication will
    provide the necessary permissions to run the policy locally.

    :example:

    .. code-block:: yaml

        policies:
            - name: role-assignment-owner
              resource: azure.roleassignment
              filters:
                - type: role
                  key: properties.roleName
                  op: eq
                  value: Owner
    """

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

        principal_dics = GraphHelper.get_principal_dictionary(graph_client, object_ids)

        for resource in resources:
            if resource['properties']['principalId'] in principal_dics.keys():
                graph_resource = principal_dics[resource['properties']['principalId']]
                if graph_resource.object_id:
                    resource['principalName'] = GraphHelper.get_principal_name(graph_resource)
                    resource['displayName'] = graph_resource.display_name
                    resource['aadType'] = graph_resource.object_type

        return resources


@resources.register('roledefinition')
class RoleDefinition(QueryResourceManager):
    """Role definitions define sets of permissions that can be assigned
    to an identity.

    :example:

    .. code-block:: yaml

        policies:
            - name: role-definition-permissions
              resource: azure.roledefinition
              filters:
                - type: value
                  key: properties.permissions[].actions[]
                  value: Microsoft.Authorization/*/read
                  op: contains
    """

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


def is_scope(scope, scope_type):
    if not isinstance(scope, six.string_types):
        return False

    regex = ""
    if scope_type == "subscription":
        regex = r"^\/subscriptions\/[^\/]+$"
    elif scope_type == "resource-group":
        regex = r"^\/subscriptions\/([^\/]+)\/resourceGroups\/.*$"
    else:
        return False

    return bool(re.match(regex, scope, flags=re.IGNORECASE))


@RoleAssignment.filter_registry.register('role')
class RoleFilter(RelatedResourceFilter):
    """Filters role assignments based on role definitions

    :example:

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

    :example:

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
        related = self.manager.get_resource_manager(self.factory.type).resources()
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


@RoleAssignment.filter_registry.register('scope')
class ScopeFilter(Filter):
    """
    Filter role assignments by assignment scope.

    :examples:

    Role assignments that have subscription level scope access

    .. code-block:: yaml

        policies:
          - name: assignments-with-subscription-scope
            resource: azure.roleassignment
            filters:
              - type: scope
                value: subscription


    Role assignments with scope other than Subscription or Resource Group.

    .. code-block:: yaml

        policies:
           - name: assignments-other-level-scope
             resource: azure.roleassignment
             filters:
                - not:
                  - type: scope
                    value: subscription
                - not:
                  - type: scope
                    value: resource-group

    """

    schema = type_schema(
        'scope',
        value={'type': 'string', 'enum': ['subscription', 'resource-group']})

    def process(self, data, event=None):
        scope_value = self.data.get('value', '')
        return [d for d in data if is_scope(d["properties"]["scope"], scope_value)]


@RoleAssignment.action_registry.register('delete')
class DeleteAssignmentAction(AzureBaseAction):

    schema = type_schema('delete')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.role_assignments.delete(
            resource['properties']['scope'], resource['name'])
