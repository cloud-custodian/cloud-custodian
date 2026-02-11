# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters import ValueFilter
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import (
    QueryResourceManager,
    TypeInfo,
    DescribeWithResourceTags,
    DescribeSource,
    sources,
    ResourceQuery,
)
from c7n.utils import local_session, type_schema


@resources.register('vpc-lattice-service-network')
class VPCLatticeServiceNetwork(QueryResourceManager):
    """VPC Lattice Service Network Resource"""

    source_mapping = {
        'describe': DescribeWithResourceTags,
    }

    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_service_networks', 'items', None)
        arn = 'arn'
        id = 'id'
        name = 'name'
        universal_taggable = object()
        permissions_enum = ('vpc-lattice:ListServiceNetworks',)
        permissions_augment = ('vpc-lattice:ListTagsForResource',)


@resources.register('vpc-lattice-service')
class VPCLatticeService(QueryResourceManager):
    """VPC Lattice Service Resource"""

    source_mapping = {
        'describe': DescribeWithResourceTags,
    }

    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_services', 'items', None)
        detail_spec = ('get_service', 'serviceIdentifier', 'id', None)
        arn = 'arn'
        id = 'id'
        name = 'name'
        universal_taggable = object()
        permissions_enum = ('vpc-lattice:ListServices',)
        permissions_augment = (
            'vpc-lattice:GetService',
            'vpc-lattice:ListTagsForResource',
        )


@resources.register('vpc-lattice-target-group')
class VPCLatticeTargetGroup(QueryResourceManager):
    """VPC Lattice Target Group Resource"""

    source_mapping = {
        'describe': DescribeWithResourceTags,
    }

    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_target_groups', 'items', None)
        detail_spec = ('get_target_group', 'targetGroupIdentifier', 'id', None)
        arn = 'arn'
        id = 'id'
        name = 'name'
        universal_taggable = object()
        permissions_enum = ('vpc-lattice:ListTargetGroups',)
        permissions_augment = (
            'vpc-lattice:GetTargetGroup',
            'vpc-lattice:ListTagsForResource',
        )


class ServiceNetworkAssociationQuery(ResourceQuery):
    """Custom query that iterates through service networks to find all associations."""

    def filter(self, resource_manager, **params):
        client = local_session(self.session_factory).client('vpc-lattice')

        # Get all service networks
        paginator = client.get_paginator('list_service_networks')
        networks = []
        for page in paginator.paginate():
            networks.extend(page.get('items', []))

        # Get associations for each service network
        associations = []
        seen_ids = set()
        for network in networks:
            try:
                assoc_paginator = client.get_paginator('list_service_network_vpc_associations')
                for page in assoc_paginator.paginate(serviceNetworkIdentifier=network['id']):
                    for assoc in page.get('items', []):
                        if assoc['id'] not in seen_ids:
                            associations.append(assoc)
                            seen_ids.add(assoc['id'])
            except client.exceptions.ResourceNotFoundException:
                continue

        return associations


@sources.register('describe-service-network-association')
class DescribeServiceNetworkAssociation(DescribeSource):
    """Custom source that lists associations by iterating through service networks."""

    resource_query_factory = ServiceNetworkAssociationQuery


@resources.register('vpc-lattice-service-network-association')
class VPCLatticeServiceNetworkAssociation(QueryResourceManager):
    """VPC Lattice Service Network VPC Association Resource

    Resource to list the lattice service network to VPC associations

    :example:

    .. code-block:: yaml

        policies:
          - name: find-active-associations
            resource: aws.vpc-lattice-service-network-association
            filters:
              - type: value
                key: status
                value: ACTIVE
    """

    source_mapping = {
        'describe': DescribeServiceNetworkAssociation,
    }

    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_service_network_vpc_associations', 'items', None)
        arn = 'arn'
        id = 'id'
        name = 'id'
        universal_taggable = object()
        permissions_enum = (
            'vpc-lattice:ListServiceNetworks',
            'vpc-lattice:ListServiceNetworkVpcAssociations',
        )
        permissions_augment = ('vpc-lattice:ListTagsForResource',)


@VPCLatticeServiceNetwork.filter_registry.register('access-logs')
@VPCLatticeService.filter_registry.register('access-logs')
class AccessLogsFilter(ValueFilter):
    """Filter VPC Lattice resources by access log subscription configuration."""

    permissions = ('vpc-lattice:ListAccessLogSubscriptions',)
    schema = type_schema('access-logs', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('vpc-lattice')
        for r in resources:
            if 'AccessLogSubscriptions' not in r:
                log_subs = self.manager.retry(
                    client.list_access_log_subscriptions,
                    resourceIdentifier=r['arn'],
                    ignore_err_codes=('ResourceNotFoundException',),
                )
                r['AccessLogSubscriptions'] = log_subs.get('items', []) if log_subs else []

        return super(AccessLogsFilter, self).process(resources, event)


@VPCLatticeServiceNetwork.filter_registry.register('cross-account')
@VPCLatticeService.filter_registry.register('cross-account')
class LatticeAuthPolicyFilter(CrossAccountAccessFilter):
    """Filter VPC Lattice resources by cross-account access in auth policy."""

    permissions = ('vpc-lattice:GetAuthPolicy',)
    policy_annotation = "c7n:AuthPolicy"

    def get_resource_policy(self, r):
        if self.policy_annotation in r:
            return r[self.policy_annotation]

        client = local_session(self.manager.session_factory).client('vpc-lattice')

        result = self.manager.retry(
            client.get_auth_policy,
            resourceIdentifier=r['arn'],
            ignore_err_codes=('ResourceNotFoundException',),
        )

        if result and result.get('policy'):
            r[self.policy_annotation] = result['policy']
            return result['policy']

        return None
