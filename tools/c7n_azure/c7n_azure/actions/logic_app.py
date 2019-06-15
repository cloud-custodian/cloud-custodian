# Copyright 2019 Microsoft Corporation
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

from azure.mgmt.logic import logic_management_client

from c7n.actions.webhook import Webhook
from c7n.utils import type_schema


class LogicAppAction(Webhook):
    """Calls an Azure Logic App with optional parameters
       and body populated from JMESPath queries.

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

        # type: logic_management_client.LogicManagementClient
        client = self.manager.get_client(
            'azure.mgmt.logic.logic_management_client.LogicManagementClient')

        callback = client.workflow_triggers.list_callback_url(
            resource_group,
            workflow_name,
            'manual')

        return callback.value
