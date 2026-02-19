# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo


@resources.register('directconnect')
class DirectConnect(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'directconnect'
        enum_spec = ('describe_connections', 'connections', None)
        id = 'connectionId'
        name = 'connectionName'
        filter_name = 'connectionId'
        filter_type = 'scalar'
        arn_type = "dxcon"
        universal_taggable = object()


@resources.register('directconnect-gateway')
class DirectConnectGateway(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'directconnect'
        enum_spec = ('describe_direct_connect_gateways', 'directConnectGateways', None)
        id = 'directConnectGatewayId'
        name = 'directConnectGatewayName'
        filter_name = 'directConnectGatewayId'
        filter_type = 'scalar'
        arn_type = 'dx-gateway'
        global_resource = True
        universal_taggable = object()


@resources.register('directconnect-virtual-interface')
class VirtualInterface(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'directconnect'
        enum_spec = ('describe_virtual_interfaces', 'virtualInterfaces', None)
        id = 'virtualInterfaceId'
        name = 'virtualInterfaceName'
        filter_name = 'virtualInterfaceId'
        filter_type = 'scalar'
        arn_type = 'dxvif'
        universal_taggable = object()
