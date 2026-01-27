# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('servicebus-namespace')
class ServiceBusNamespace(ArmResourceManager):

    """Azure Service Bus Namespace Resource

    :example:

    Returns Service Bus Namespace resources

    .. code-block:: yaml

         policies:
          - name: basic-servicebus-namespace
            resource: azure.servicebus-namespace
            filters:
              - type: value
                key: authorizationRules
                value: present

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Events']

        service = 'azure.mgmt.servicebus'
        client = 'ServiceBusManagementClient'
        enum_spec = ('namespaces', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.ServiceBus/namespaces'
