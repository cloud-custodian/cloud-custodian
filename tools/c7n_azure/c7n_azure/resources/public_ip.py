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

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n.filters.core import type_schema
from c7n.actions import BaseAction


@resources.register('publicip')
class PublicIPAddress(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('public_ip_addresses', 'list_all', None)
        type = 'publicip'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.publicIPAddressVersion',
            'properties.publicIPAllocationMethod',
            'properties.ipAddress'
        )


@PublicIPAddress.action_registry.register('delete')
class PublicIPDeleteAction(BaseAction):

    schema = type_schema('delete')

    def __init__(self, data=None, manager=None, log_dir=None):
        super(PublicIPDeleteAction, self).__init__(data, manager, log_dir)
        self.client = self.manager.get_client()

    def delete(self, resource_group, public_ip_name):
        self.client.public_ip_addresses.delete(resource_group, public_ip_name)

    def process(self, public_ips):
        for public_ip in public_ips:
            self.delete(public_ip['resourceGroup'], public_ip['name'])
