# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('logic-app-workflow')
class LogicAppWorkflow(ArmResourceManager):
    """Azure Logic App Resource

    :example:

    Returns all Logic Apps Workflows

    .. code-block:: yaml

        policies:
          - name: basic-logic-app
            resource: azure.logic-app-workflow
            filters:
              - type: value
                key: sku.name
                op: equal
                value: Basic

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute']

        service = 'azure.mgmt.logic'
        client = 'LogicManagementClient'
        enum_spec = ('workflows', 'list_by_subscription', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Logic/workflows'
