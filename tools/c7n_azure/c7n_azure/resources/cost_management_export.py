# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import logging

from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager
from c7n_azure.utils import ThreadHelper

from c7n.filters import Filter
from c7n.utils import get_annotation_prefix
from c7n.utils import type_schema

log = logging.getLogger('c7n.azure.cost-management-export')


@resources.register('cost-management-export')
class CostManagementExport(QueryResourceManager):
    """ Cost Management Exports for current subscription (doesn't include Resource Group scopes)

    :example:

    Returns all cost exports for current subscription scope

    .. code-block:: yaml

        policies:
          - name: get-cost-management-exports
            resource: azure.cost-management-export

    """

    class resource_type(QueryResourceManager.resource_type):
        doc_groups = ['Cost']

        service = 'azure.mgmt.costmanagement'
        client = 'CostManagementClient'
        enum_spec = ('exports', 'list', None)
        default_report_fields = (
            'name',
            'properties.deliveryInfo.destination.resourceId'
        )
        resource_type = 'Microsoft.CostManagement/exports'

        @classmethod
        def extra_args(cls, resource_manager):
            scope = '/subscriptions/{0}'\
                .format(resource_manager.get_session().get_subscription_id())
            return {'scope': scope}


@CostManagementExport.filter_registry.register('last-execution')
class CostManagementExportFilterLastExecution(Filter):
    """ Find Cost Management Exports with last execution more than X days ago.

    :example:

    Returns all cost exports that didn't run in last 30 days.

    .. code-block:: yaml

        policies:
          - name: find-stale-management-exports
            resource: azure.cost-management-export
            filters:
              - type: last-execution
                age: 30
    """

    schema = type_schema(
        'last-execution',
        required=['age'],
        **{
            'age': {'type': 'integer', 'minimum': 0}
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
            if get_annotation_prefix('last-execution') in r:
                continue
            history = self.client.exports.get_execution_history(self.scope, r['name'])

            # Include exports that has no execution history
            if not history.value:
                r[get_annotation_prefix('last-execution')] = 'None'
                result.append(r)
                continue

            last_execution = max(history.value, key=lambda execution: execution.submitted_time)
            if last_execution.submitted_time.date() <= self.min_date.date():
                r[get_annotation_prefix('last-execution')] = last_execution.serialize(True)
                result.append(r)

        return result


@CostManagementExport.action_registry.register('execute')
class CostManagementExportActionExecute(AzureBaseAction):
    """ Trigger Cost Management Export execution

    Known issues:

    If you see an error
    ``Error: (400) A valid email claim is required. Email claim is missing in the request header.``
    please ensure used Service Principal has proper email configured.

    :example:

    Find all exports that have not been executed in the last 30 days and then
    trigger a manual export.

    .. code-block:: yaml

        policies:
          - name: execute-stale-management-exports
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
