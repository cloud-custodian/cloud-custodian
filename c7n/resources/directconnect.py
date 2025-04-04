# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import universal_augment


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
        permissions_augment = ("directconnect:DescribeTags",)

    augment = universal_augment


@resources.register('directconnect-virtual-interface')
class DirectConnectVirtualInterface(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'directconnect'
        enum_spec = ('describe_virtual_interfaces', 'virtualInterfaces', None)
        id = 'virtualInterfaceId'
        name = 'virtualInterfaceName'
        filter_name = 'virtualInterfaceId'
        filter_type = 'scalar'  # TODO list?
        arn_type = "dxvif"
        universal_taggable = object()
        permissions_augment = ("directconnect:DescribeTags",)

    augment = universal_augment


# TODO directconnect-gateway resource itself


class DirectConnectGatewayAssociationDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))

@resources.register('directconnect-gateway-association')
class DirectConnectGatewayAssociation(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'directconnect'
        enum_spec = (
            'describe_direct_connect_gateway_associations',
            'directConnectGatewayAssociations',
            None
        )
        id = 'associationId'
        name = 'associationId'
        filter_name = 'associationId'
        filter_type = 'scalar'  # TODO list?
        arn_type = 'dx-gateway'
        universal_taggable = object()
        permissions_augment = ("directconnect:DescribeTags",)

    augment = universal_augment
