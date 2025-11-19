# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters import ValueFilter
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeWithResourceTags
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
            'vpc-lattice:ListTagsForResource'
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
            'vpc-lattice:ListTagsForResource'
        )


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
                    ignore_err_codes=('ResourceNotFoundException',)
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
            ignore_err_codes=('ResourceNotFoundException',)
        )

        if result and result.get('policy'):
            r[self.policy_annotation] = result['policy']
            return result['policy']

        return None
