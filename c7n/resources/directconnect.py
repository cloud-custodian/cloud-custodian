# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema
from c7n.filters import ValueFilter


@resources.register('directconnect')
class DirectConnect(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'directconnect'
        enum_spec = ('describe_connections', 'connections', None)
        id = 'connectionId'
        name = 'connectionName'
        filter_name = 'connectionId'
        arn_type = "dxcon"
        universal_taggable = object()

    augment = universal_augment


@resources.register('directconnect-vif')
class DirectConnectVirtualInterface(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'directconnect'
        enum_spec = ('describe_virtual_interfaces', 'virtualInterfaces', None)
        id = filter_name = 'virtualInterfaceId'
        name = 'virtualInterfaceName'
        filter_type = 'scalar'
        arn_type = "dxvif"
        universal_taggable = object()


@resources.register('directconnect-gateway')
class DirectConnectGateway(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'directconnect'
        enum_spec = ('describe_direct_connect_gateways', 'directConnectGateways', None)
        id = filter_name = 'directConnectGatewayId'
        name = 'directConnectGatewayName'
        filter_type = 'scalar'
        arn_type = "dx-gateway"


@DirectConnectGateway.filter_registry.register('associations')
class DirectConnectGatewayAssociations(ValueFilter):
    """Filters Direct Connect Gateways by attached Associations

    This pulls a Direct Connect Gateway resource's Assocations and adds
    them as a new field to each resource, and allows us to filter resources
    based on these Associations.

    An example of this is filtering Gateway resources to find any instances
    associated with resources in an AWS account outside of a provided whitelist.
    """
    schema = type_schema('associations', rinherit=ValueFilter.schema)
    permissions = ('directconnect:DescribeDirectConnectGatewayAssociations',)
    annotation_key = 'c7n:directConnectGatewayAssociations'

    def process(self, resources, event=None):

        client = local_session(self.manager.session_factory).client('directconnect')

        def _augment(r):
            try:
                r[self.annotation_key] = self.manager.retry(
                    client.describe_direct_connect_gateway_associations,
                    directConnectGatewayId=r['directConnectGatewayId']).get(
                    'directConnectGatewayAssociations')
            except ClientError as e:
                if e.response['Error']['Code'] == "AccessDeniedException":
                    self.log.warning(
                        f"""Access denied getting Direct Connect Gateway Associations for Gateway:
                            {r['directConnectGatewayName']}"""
                    )
                raise
            return r

        with self.executor_factory(max_workers=3) as w:
            results = []
            resources = list(filter(None, w.map(_augment, resources)))
            for r in resources:
                for association in r[self.annotation_key]:
                    if self.match(association):
                        results.append(r)
                        break
            return results
