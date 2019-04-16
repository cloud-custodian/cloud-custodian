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
from c7n.filters.core import ValueFilter, type_schema
from c7n.utils import chunks
from concurrent.futures import as_completed
import logging

log = logging.getLogger('azure.networkinterface')

@resources.register('networkinterface')
class NetworkInterface(ArmResourceManager):
    class resource_type(object):
        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('network_interfaces', 'list_all', None)
        id = 'id'
        name = 'name'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )


@NetworkInterface.filter_registry.register('effective-route-table')
class EffectiveRouteTableFilter(ValueFilter):
    schema = type_schema('effective-route-table', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        futures = []
        results = []
        chunk_size = 20

        # Process each resource in a separate thread, returning all that pass filter
        with self.executor_factory(max_workers=3) as w:
            for resource_set in chunks(resources, chunk_size):
                futures.append(w.submit(self.process_resource_set, resource_set))

            for f in as_completed(futures):
                if f.exception():
                    self.log.warning(
                        "Diagnostic settings filter error: %s" % f.exception())
                    continue
                else:
                    results.extend(f.result())

            return results

    def process_resource_set(self, resources):
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
                    filtered_effective_route_table = super(EffectiveRouteTableFilter, self).process([resource], event=None)

                    if filtered_effective_route_table:
                        matched.append(resource)

            except Exception as error:
                log.warning(error)

        return matched
