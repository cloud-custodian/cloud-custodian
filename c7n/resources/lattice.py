# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json

from c7n.filters import Filter
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.utils import local_session, type_schema
from c7n import tags
from c7n.tags import universal_augment


class DescribeServiceNetwork(DescribeSource):
    """Augments Service Network resources."""

    def augment(self, resources):
        return universal_augment(self.manager, resources)


class DescribeService(DescribeSource):
    """Augments Service resources with auth type."""

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('vpc-lattice')

        for r in resources:
            details = self.manager.retry(
                client.get_service,
                serviceIdentifier=r['id'],
                ignore_err_codes=('ResourceNotFoundException',)
            )
            if details:
                r.update(details)
            else:
                r['authType'] = 'NONE'

        return universal_augment(self.manager, resources)


class DescribeTargetGroup(DescribeSource):
    """Augments Target Group resources with details."""

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('vpc-lattice')

        for r in resources:
            details = self.manager.retry(
                client.get_target_group,
                targetGroupIdentifier=r['id'],
                ignore_err_codes=('ResourceNotFoundException',)
            )
            if details:
                r.update(details)

        return universal_augment(self.manager, resources)


@resources.register('vpc-lattice-service-network')
class VPCLatticeServiceNetwork(QueryResourceManager):
    """VPC Lattice Service Network Resource"""

    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_service_networks', 'items', None)
        arn = 'arn'
        id = 'id'
        name = 'name'
        universal_taggable = object()
        permissions_enum = ('vpc-lattice:ListServiceNetworks',)
        permissions_augment = (
            'vpc-lattice:ListTagsForResource',
            'vpc-lattice:GetResourcePolicy',
            'vpc-lattice:GetAuthPolicy'
        )

    source_mapping = {
        'describe': DescribeServiceNetwork,
    }


@resources.register('vpc-lattice-service')
class VPCLatticeService(QueryResourceManager):
    """VPC Lattice Service Resource"""

    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_services', 'items', None)
        arn = 'arn'
        id = 'id'
        name = 'name'
        universal_taggable = object()
        permissions_enum = ('vpc-lattice:ListServices',)
        permissions_augment = (
            'vpc-lattice:ListTagsForResource',
            'vpc-lattice:GetResourcePolicy',
            'vpc-lattice:GetAuthPolicy'
        )

    source_mapping = {
        'describe': DescribeService,
    }


@resources.register('vpc-lattice-target-group')
class VPCLatticeTargetGroup(QueryResourceManager):
    """VPC Lattice Target Group Resource"""

    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_target_groups', 'items', None)
        arn = 'arn'
        id = 'id'
        name = 'name'
        universal_taggable = object()
        permissions_enum = ('vpc-lattice:ListTargetGroups',)
        permissions_augment = (
            'vpc-lattice:GetTargetGroup',
            'vpc-lattice:ListTagsForResource'
        )

    source_mapping = {
        'describe': DescribeTargetGroup,
    }


@VPCLatticeServiceNetwork.filter_registry.register('access-logs')
@VPCLatticeService.filter_registry.register('access-logs')
class AccessLogsFilter(Filter):
    """Filters VPC Lattice resources by access logging configuration."""

    schema = type_schema(
        'access-logs',
        enabled={'type': 'boolean', 'default': True},
        destination_type={'type': 'string', 'enum': ['s3', 'cloudwatch', 'firehose']},
        log_types={'type': 'array', 'items': {'type': 'string', 'enum': ['SERVICE', 'RESOURCE']}},
        check_all_types={'type': 'boolean', 'default': True}
    )
    permissions = ('vpc-lattice:ListAccessLogSubscriptions',)

    def process(self, resources, event=None):
        enabled = self.data.get('enabled', True)
        dest_type = self.data.get('destination_type')
        required_types = self.data.get('log_types')
        is_network = self.manager.resource_type.name == 'vpc-lattice-service-network'

        check_types = None
        if is_network:
            check_types = set(required_types or ['SERVICE', 'RESOURCE'])

        client = local_session(self.manager.session_factory).client('vpc-lattice')
        results = []

        for r in resources:
            if 'c7n:AccessLogSubscriptions' not in r:
                log_subs = self.manager.retry(
                    client.list_access_log_subscriptions,
                    resourceIdentifier=r['arn'],
                    ignore_err_codes=('ResourceNotFoundException',)
                )
                r['c7n:AccessLogSubscriptions'] = log_subs.get('items', []) if log_subs else []

            subs = r['c7n:AccessLogSubscriptions']
            has_logs = False

            if is_network:
                found_types = {s.get('serviceNetworkLogType') for s in subs}
                has_logs = check_types.issubset(found_types)
            else:
                has_logs = len(subs) > 0

            if dest_type and has_logs:
                has_correct_dest = any(
                    (dest_type == 's3' and 'arn:aws:s3:::'
                      in s.get('destinationArn', '')) or
                    (dest_type == 'cloudwatch' and 'arn:aws:logs:'
                      in s.get('destinationArn', '')) or
                    (dest_type == 'firehose' and 'arn:aws:firehose:'
                     in s.get('destinationArn', ''))
                    for s in subs
                )
                has_logs = has_correct_dest

            if has_logs == enabled:
                results.append(r)
        return results


@VPCLatticeServiceNetwork.filter_registry.register('cross-account')
@VPCLatticeService.filter_registry.register('cross-account')
class LatticeResourcePolicyFilter(CrossAccountAccessFilter):
    """Filter VPC Lattice resources by resource or auth policy cross-account access."""

    permissions = ('vpc-lattice:GetResourcePolicy', 'vpc-lattice:GetAuthPolicy',)
    policy_annotation = "c7n:Policy"

    def get_resource_policy(self, r):
        if self.policy_annotation in r:
            return r[self.policy_annotation]

        client = local_session(self.manager.session_factory).client('vpc-lattice')

        for method, param in [
            ('get_resource_policy', 'resourceArn'),
            ('get_auth_policy', 'resourceIdentifier')
        ]:
            result = self.manager.retry(
                getattr(client, method),
                **{param: r['arn']},
                ignore_err_codes=('ResourceNotFoundException',)
            )

            if result and result.get('policy'):
                policy = json.loads(result['policy'])
                r[self.policy_annotation] = policy
                return policy

        return None


VPCLatticeServiceNetwork.filter_registry.register('tag-count', tags.TagCountFilter)
VPCLatticeServiceNetwork.filter_registry.register('marked-for-op', tags.TagActionFilter)
VPCLatticeService.filter_registry.register('tag-count', tags.TagCountFilter)
VPCLatticeService.filter_registry.register('marked-for-op', tags.TagActionFilter)
VPCLatticeTargetGroup.filter_registry.register('tag-count', tags.TagCountFilter)
VPCLatticeTargetGroup.filter_registry.register('marked-for-op', tags.TagActionFilter)
