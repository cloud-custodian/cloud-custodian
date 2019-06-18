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

from c7n_azure import constants
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager

from c7n.filters.core import ValueFilter, type_schema
from c7n_azure.utils import ThreadHelper
import logging

max_workers = constants.DEFAULT_MAX_THREAD_WORKERS
chunk_size = constants.DEFAULT_CHUNK_SIZE
log = logging.getLogger('custodian.azure.networkinterface')


@resources.register('networkinterface')
class NetworkInterface(ArmResourceManager):
    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('network_interfaces', 'list_all', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'Microsoft.Network/networkInterfaces'


@NetworkInterface.filter_registry.register('effective-route-table')
class EffectiveRouteTableFilter(ValueFilter):
    schema = type_schema('effective-route-table', rinherit=ValueFilter.schema)
    schema_alias = False
    def process(self, resources, event=None):

        resources, _ = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resource_set,
            executor_factory=self.executor_factory,
            log=log,
            max_workers=max_workers,
            chunk_size=chunk_size
        )
        return resources

    def _process_resource_set(self, resources, event):
        client = self.manager.get_client()
        matched = []

        for resource in resources:
            try:
                if 'routes' not in resource:
                    route_table = (
                        client.network_interfaces
                        .get_effective_route_table(resource['resourceGroup'], resource['name'])
                        .result()
                    )

                    resource['routes'] = route_table.serialize()
                    filtered_effective_route_table = super(EffectiveRouteTableFilter, self)\
                        .process([resource], event)

                    if filtered_effective_route_table:
                        matched.append(resource)

            except Exception as error:
                log.warning(error)

        return matched
