# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager

from c7n.filters.core import type_schema


@resources.register('eventsubscription')
class EventSubscription(QueryResourceManager):

    class resource_type(QueryResourceManager.resource_type):
        doc_groups = ['Events']

        service = 'azure.mgmt.eventgrid'
        client = 'EventGridManagementClient'
        enum_spec = ('event_subscriptions', 'list_global_by_subscription', None)
        default_report_fields = (
            'name',
            'properties.destination.endpointType',
            'properties.topic'
        )


@EventSubscription.action_registry.register('delete')
class Delete(AzureBaseAction):
    schema = type_schema('delete')

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        self.client.event_subscriptions.begin_delete(
            resource['properties']['topic'], resource['name'])
