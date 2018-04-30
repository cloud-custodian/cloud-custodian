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


@resources.register('publicip')
class PublicIPAddress(QueryResourceManager):

    class resource_type(object):
        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('public_ip_addresses', 'list_all')
        id = 'id'
        type = 'publicip'
        name = 'name'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.publicIPAddressVersion',
            'properties.publicIPAllocationMethod',
            'properties.ipAddress'
        )

    def get_resources(self, resource_ids):
        result = []
        for resource_id in resource_ids:
            resource_group = resource_id.split('/')[4]
            name = resource_id.split('/')[8]
            r = self.get_client().public_ip_addresses.get(resource_group, name)
            result.append(r.serialize(True))
        return result
