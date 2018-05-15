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
from c7n.filters.core import ValueFilter, type_schema
from c7n.filters.related import RelatedResourceFilter


@resources.register('loadbalancer')
class LoadBalancer(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('load_balancers', 'list_all')
        type = 'loadbalancer'


@LoadBalancer.filter_registry.register('frontend-public-ip')
class FrontEndIp(RelatedResourceFilter):
    """Filters load balancers by frontend public ip.

    :Example:

        .. code-block:: yaml

            policies:
               - name: loadbalancer-with-ipv6-frontend
                 resource: azure.loadbalancer
                 filters:
                    - type: frontend-public-ip
                      key: properties.publicIPAddressVersion
                      op: in
                      value_type: normalize
                      value: "ipv6"
    """

    schema = type_schema('frontend-public-ip', rinherit=ValueFilter.schema)

    RelatedResource = "c7n_azure.resources.public_ip.PublicIPAddress"
    RelatedIdsExpression = "properties.frontendIPConfigurations[].properties.publicIPAddress.id"
