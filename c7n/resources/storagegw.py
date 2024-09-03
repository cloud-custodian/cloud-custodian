# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import universal_augment


@resources.register('storage-gateway')
class StorageGateway(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'storagegateway'
        enum_spec = ('list_gateways', 'Gateways', None)
        detail_spec = ('describe_gateway_information', 'GatewayARN', 'GatewayARN', None)
        arn = id = 'GatewayARN'
        arn_type = 'gateway'
        name = 'GatewayName'
        universal_taggble = object()
