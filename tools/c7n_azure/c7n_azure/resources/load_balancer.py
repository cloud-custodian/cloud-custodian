# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager

from c7n.filters.core import ValueFilter, type_schema
from c7n.filters.related import RelatedResourceFilter


@resources.register('loadbalancer')
class LoadBalancer(ArmResourceManager):
    """Load Balancer Resource

    :example:

    This policy will filter load balancers with an ipv6 frontend public IP

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

    :example:

    This policy will find all load balancers with 1000 or less transmitted packets
    over the last 72 hours

    .. code-block:: yaml

        policies:
          - name: notify-inactive-loadbalancer
            resource: azure.loadbalancer
            filters:
              - type: metric
                metric: PacketCount
                op: le
                aggregation: total
                threshold: 1000
                timeframe: 72


    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Networking']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('load_balancers', 'list_all', None)
        resource_type = 'Microsoft.Network/loadBalancers'


@LoadBalancer.filter_registry.register('frontend-public-ip')
class FrontEndIp(RelatedResourceFilter):
    """Filters load balancers by frontend public ip.

    :example:

    Find all load balancers with a ipv6 public front end.

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
