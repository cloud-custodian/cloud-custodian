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

from c7n_azure.query import QueryResourceManager
from c7n_azure.provider import resources
from c7n.filters.core import ValueFilter, type_schema


@resources.register('vm')
class VirtualMachine(QueryResourceManager):

    class resource_type(object):
        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        enum_spec = ('virtual_machines', 'list_all')
        id = 'id'
        name = 'name'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.hardwareProfile.vmSize',
        )


@VirtualMachine.filter_registry.register('instance-view')
class InstanceViewFilter(ValueFilter):
    schema = type_schema('instance-view', rinherit=ValueFilter.schema)

    def __call__(self, i):
        if 'instanceView' not in i:
            client = self.manager.get_client()
            instance = (
                client.virtual_machines
                .get(i['resourceGroup'], i['name'], expand='instanceview')
                .instance_view
            )
            i['instanceView'] = instance.serialize()

        return super(InstanceViewFilter, self).__call__(i['instanceView'])
