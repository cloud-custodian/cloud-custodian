# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.actions.webhook import Webhook
from c7n.utils import type_schema


class LogicAppAction(Webhook):
    """
    Calls an Azure Logic App with optional parameters and body populated from JMESPath queries.
    Your policy credentials are used to get the trigger endpoint URL with secrets
    using the resource group and app name.

    This action is based on the ``webhook`` action and supports the same options.

    :example:

    This policy will call logic app with list of VM's

        .. code-block:: yaml

          policies:
            - name: call-logic-app
              resource: azure.vm
              description: |
                Call logic app with list of VM's
              actions:
               - type: logic-app
                 resource-group: custodian-test
                 logic-app-name: cclogicapp
                 batch: true
                 body: 'resources[].{ vm_name: name }'
    """

    schema = type_schema(
        'logic-app',
        required=['resource-group', 'logic-app-name'],
        rinherit=Webhook.schema,
        url=None,
        **{
            'resource-group': {'type': 'string'},
            'logic-app-name': {'type': 'string'}
        }
    )

    def __init__(self, data=None, manager=None, log_dir=None):
        super(LogicAppAction, self).__init__(data, manager, log_dir)
        self.method = 'POST'

    def process(self, resources, event=None):
        self.url = self.get_callback_url(
            self.data.get('resource-group'),
            self.data.get('logic-app-name'))

        super(LogicAppAction, self).process(resources, event)

    def get_callback_url(self, resource_group, workflow_name):
        """ Gets the logic app invoke trigger with secrets using RBAC """

        client = self.manager.get_client(
            'azure.mgmt.logic.LogicManagementClient')

        callback = client.workflow_triggers.list_callback_url(
            resource_group,
            workflow_name,
            'manual')

        return callback.value
