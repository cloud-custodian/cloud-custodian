# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources


@resources.register('application-gateway')
class ApplicationGateway(ArmResourceManager):
    """Azure Application Gateway

    :example:

    This policy will find all Application Gateways

    .. code-block:: yaml

        policies:
          - name: app_gateways
            resource: azure.application-gateway

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Network']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('application_gateways', 'list_all', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Network/applicationGateways'
