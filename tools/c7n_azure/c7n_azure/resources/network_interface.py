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

    def __call__(self, i):
        if 'routes' not in i:
            client = self.manager.get_client()

            try:
                route_table = (
                    client.network_interfaces
                        .get_effective_route_table(i['resourceGroup'], i['name'])
                        .result()
                )

                i['routes'] = route_table.serialize()
            except Exception as error:
                log.warning(error)

        return super(EffectiveRouteTableFilter, self).__call__(i)
