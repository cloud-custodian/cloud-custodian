# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.query import ChildResourceManager, ChildTypeInfo
from c7n_azure.utils import ResourceIdParser


@resources.register('servicebus-namespace-authrules')
class ServiceBusNamespaceAuthRules(ChildResourceManager):
    """Azure Service Bus Namespace Authorization Rules Resource

    :example:

    Returns Service Bus Namespace Authorization Rule resources

    .. code-block:: yaml

         policies:
          - name: basic-servicebus-namespace-auth
            resource: azure.servicebus-namespace-authrules
            filters:
            - type: value
              key: properties.rights
              op: contains
              value: Manage

    """

    class resource_type(ChildTypeInfo):
        doc_groups = ['Events']

        service = 'azure.mgmt.servicebus'
        client = 'ServiceBusManagementClient'
        enum_spec = ('namespaces', 'list_authorization_rules', None)
        parent_manager_name = 'servicebus-namespace'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.ServiceBus/namespaces'

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': ResourceIdParser.get_resource_group(parent_resource['id']),
                'namespace_name': parent_resource['name']
            }
