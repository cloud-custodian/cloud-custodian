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

from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager
from c7n_azure.utils import ThreadHelper

from c7n.filters import Filter
from c7n.utils import get_annotation_prefix as gap
from c7n.utils import type_schema
import logging

import datetime


log = logging.getLogger('c7n.azure.cost-management-export')


@resources.register('cost-management-export')
class CostManagementExport(QueryResourceManager):
    """ Cost Management Exports for current subscription (doesn't include Resource Group scopes)

    :example:

    Returns all cost exports for current subscription scope

    .. code-block:: yaml

        policies:
          - name: get-cost--management-exports
            resource: azure.cost-management-export

    """

    class resource_type(QueryResourceManager.resource_type):
        doc_groups = ['Cost']

        service = 'azure.mgmt.costmanagement'
        client = 'CostManagementClient'
        enum_spec = ('exports', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
        )
        resource_type = 'Microsoft.Compute/images'

        @classmethod
        def extra_args(cls, resource_manager):
            scope = '/subscriptions/{0}'\
                .format(resource_manager.get_session().get_subscription_id())
            return {'scope': scope}


@CostManagementExport.filter_registry.register('last-execution')
class KeyVaultFilter(Filter):
    """ Find Cost Management Exports with last execution more than X days ago.

    Known issues:

    Error: (400) A valid email claim is required. Email claim is missing in the request header.

    :example:

    Returns all cost exports that didn't run in last 30 days.

    .. code-block:: yaml

        policies:
          - name: get-cost--management-exports
            resource: azure.cost-management-export
            filters:
              - type: last-execution
                age: 30
    """

    schema = type_schema(
        'last-execution',
        required=['age'],
        **{
            'age': {'type': 'integer'}
        }
    )

    def process(self, resources, event=None):
        self.client = self.manager.get_client()
        self.scope = 'subscriptions/{0}'.format(self.manager.get_session().get_subscription_id())
        self.min_date = datetime.datetime.now() - datetime.timedelta(days=self.data['age'])

        result, _ = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._check_resources,
            executor_factory=self.executor_factory,
            log=log
        )

        return result

    def _check_resources(self, resources, event):
        result = []

        for r in resources:
            if gap('last-execution') in r:
                continue
            history = self.client.exports.get_execution_history(self.scope, r['name'])

            # Include exports that has no execution history
            if len(history.value) == 0:
                r[gap('last-execution')] = 'None'
                result.append(r)

            last_execution = max(history.value, key=lambda a: a.submitted_time)
            if last_execution.submitted_time.date() <= self.min_date.date():
                r[gap('last-execution')] = last_execution.serialize(True)
                result.append(r)

        return result


@CostManagementExport.action_registry.register('execute')
class CostManagementExportActionExecute(AzureBaseAction):
    """ Trigger Cost Management Export execution

    Known issues:

    Error: (400) A valid email claim is required. Email claim is missing in the request header.

    :example:

    Find all exports with last execution more than 30 days and trigger manual execution.

    .. code-block:: yaml

        policies:
          - name: get-cost--management-exports
            resource: azure.cost-management-export
            filters:
              - type: last-execution
                age: 30
            actions:
              - type: execute
    """

    schema = type_schema('execute')

    def _prepare_processing(self):
        self.client = self.manager.get_client()
        self.scope = 'subscriptions/{0}'.format(self.manager.get_session().get_subscription_id())

    def _process_resource(self, resource):
        self.client.exports.execute(self.scope, resource['name'])
