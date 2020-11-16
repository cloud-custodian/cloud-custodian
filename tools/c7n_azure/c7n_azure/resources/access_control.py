# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import re

from azure.graphrbac import GraphRbacManagementClient
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import Azure
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager, DescribeSource
from c7n_azure.utils import GraphHelper

from c7n.filters import Filter
from c7n.filters import FilterValidationError
from c7n.filters import ValueFilter
from c7n.filters.related import RelatedResourceFilter
from c7n.resources import load_resources
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

    Return role assignments with the `Owner role`.

    .. code-block:: yaml

        policies:
            - name: role-assignment-owner
              resource: azure.roleassignment
              filters:
                - type: role
                  key: properties.roleName
                  op: eq
                  value: Owner

    :example:

    Return assignments with the principal name custodian@example.com

    .. code-block:: yaml

         policies:
           - name: assignment-by-principal-name
             resource: azure.roleassignment
             filters:
                - type: value
                  key: principalName
                  op: eq
                  value: custodian@example.com

    :example:

    Delete the assignment with principal name custodian@example.com.

    **Note: The permissions required to run the
    delete action requires delete permissions to Microsoft.Authorization.
    The built-in role with the necessary permissions is Owner.**

    .. code-block:: yaml

         policies:
           - name: delete-assignment-by-principal-name
             resource: azure.roleassignment
             filters:
                - type: value
                  key: principalName
                  op: eq
                  value: custodian@example.com
             actions:
                - type: delete

    """

    class resource_type(QueryResourceManager.resource_type):
        doc_groups = ['Active Directory']

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
        s = self.get_session().get_session_for_resource('https://graph.windows.net')
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

    Return role definitions that explicitly have the permission to read authorization objects (role
    assignments, role definitions, etc). If a role definition inherits permissions
    (e.g. by having * permissions) they are not returned in this filter.

    .. code-block:: yaml

        policies:
            - name: role-definition-permissions
              resource: azure.roledefinition
              filters:
                - type: value
                  key: properties.permissions[0].actions
                  value: Microsoft.Authorization/*/read
                  op: contains
    """

    class resource_type(QueryResourceManager.resource_type):
        doc_groups = ['Active Directory']

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

    :example:

    Return role assignments with the `Owner role`.

    .. code-block:: yaml

        policies:
           - name: assignments-by-role-definition
             resource: azure.roleassignment
             filters:
                - type: role
                  key: properties.roleName
                  op: in
                  value: Owner

    :example:

    Return all assignments with the `Owner role` that have access to virtual machines. For the
    resource-access filter, the related resource can be any custodian supported azure
    resource other than `azure.roleassignments` or `azure.roledefinitions`.

    .. code-block:: yaml

        policies:
           - name: assignment-by-role-and-resource
             resource: azure.roleassignment
             filters:
                - type: role
                  key: properties.roleName
                  op: eq
                  value: Owner
                - type: resource-access
                  relatedResource: azure.vm

    :example:

    Return all assignments with the `Owner role` that have access to virtual machines in `westus2`:

    .. code-block:: yaml

        policies:
           - name: assignment-by-role-and-resource-access
             resource: azure.roleassignment
             filters:
                - type: role
                  key: properties.roleName
                  op: eq
                  value: Owner
                - type: resource-access
                  relatedResource: azure.vm
                  key: location
                  op: eq
                  value: westus2
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
        load_resources((resource_type,))
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

    :example:

    Return all role assignments with the `Subscription` level scope access.

    .. code-block:: yaml

        policies:
           - name: assignments-subscription-scope
             resource: azure.roleassignment
             filters:
                - type: scope
                  value: subscription

    :example:

    Role assignments with scope other than `Subscription` or `Resource Group`.

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

    :example:

    Return all service principal role assignments with the `Subscription` level scope access.

    .. code-block:: yaml

        policies:
           - name: service-principal-assignments-subscription-scope
             resource: azure.roleassignment
             filters:
                - type: value
                  key: aadType
                  op: eq
                  value: ServicePrincipal
                - type: scope
                  value: subscription

    """

    SUBSCRIPTION_SCOPE = 'subscription'
    RG_SCOPE = 'resource-group'
    MG_SCOPE = 'management-group'

    schema = type_schema(
        'scope',
        value={'type': 'string', 'enum': [SUBSCRIPTION_SCOPE, RG_SCOPE, MG_SCOPE]})

    def process(self, data, event=None):
        scope_value = self.data.get('value', '')
        return [d for d in data if self.is_scope(d["properties"]["scope"], scope_value)]

    def is_scope(self, scope, scope_type):
        if not isinstance(scope, str):
            return False

        regex = ""
        if scope_type == self.SUBSCRIPTION_SCOPE:
            regex = r"^\/subscriptions\/[^\/]+$"
        elif scope_type == self.RG_SCOPE:
            regex = r"^\/subscriptions\/([^\/]+)\/resourceGroups\/[^\/]+$"
        elif scope_type == self.MG_SCOPE:
            regex = r"^\/providers\/Microsoft\.Management\/managementGroups/[^\/]+$"
        else:
            return False

        match = re.match(regex, scope, flags=re.IGNORECASE)

        return bool(match)


@RoleAssignment.action_registry.register('delete')
class DeleteAssignmentAction(AzureBaseAction):

    schema = type_schema('delete')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.role_assignments.delete(
            resource['properties']['scope'], resource['name'])
