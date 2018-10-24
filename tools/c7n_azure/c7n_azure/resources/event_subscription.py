# Copyright 2018 Capital One Services, LLC
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

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.query import QueryResourceManager

from c7n.actions import BaseAction
from c7n.filters.core import type_schema, Filter


@resources.register('eventsubscription')
class EventSubscription(QueryResourceManager):

    class resource_type(object):
        service = 'azure.mgmt.eventgrid'
        client = 'EventGridManagementClient'
        enum_spec = ('event_subscriptions', 'list_global_by_subscription', None)
        default_report_fields = (
            'name',
            'properties.destination.endpointType',
            'properties.topic'
        )


@EventSubscription.action_registry.register('delete')
class Delete(BaseAction):
    schema = type_schema('delete')

    def __init__(self, data=None, manager=None, log_dir=None):
        super(Delete, self).__init__(data, manager, log_dir)
        self.client = self.manager.get_client()

    def delete(self, scope, name):
        self.client.event_subscriptions.delete(scope, name)

    def process(self, resources):
        for resource in resources:
            self.delete(resource['properties']['topic'], resource['name'])
