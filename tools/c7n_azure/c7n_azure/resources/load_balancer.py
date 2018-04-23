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
from c7n.filters.related import RelatedResourceFilter

@resources.register('loadbalancer')
class LoadBalancer(QueryResourceManager):

    class resource_type(object):
        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('load_balancers', 'list_all')
        id = 'id'
        type = 'loadbalancer'
        name = 'name'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )

@LoadBalancer.filter_registry.register('frontendip')
class FrontEndIp(RelatedResourceFilter):
    # policies:
    #     - name: test - loadbalancer
    #     resource: azure.loadbalancer
    #     filters:
    #     - type: frontendip
    #         key: properties.publicIPAddressVersion
    #         op: eq
    #         value_type: normalize
    #         value: "ipv4"

    schema = type_schema('frontendip', rinherit=ValueFilter.schema)

    RelatedResource = "c7n_azure.resources.public_ip.PublicIPAddress"
    RelatedIdsExpression = "properties.frontendIPConfigurations[0].properties.publicIPAddress.id"

