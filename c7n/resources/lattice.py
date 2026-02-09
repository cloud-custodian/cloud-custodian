# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters import ValueFilter
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeWithResourceTags, ResourceQuery
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


class VPCLatticeRuleQuery(ResourceQuery):
    def filter(self, resource_manager, **params):
        m = self.resolve(resource_manager.resource_type)
        if resource_manager.get_client:
            client = resource_manager.get_client()
        else:
            client = local_session(self.session_factory).client(
                m.service, resource_manager.config.region
            )

        service_id = params.get('serviceIdentifier')
        listener_id = params.get('listenerIdentifier')

        if service_id and listener_id:
            rules = (
                self._invoke_client_enum(
                    client,
                    'list_rules',
                    {'serviceIdentifier': service_id, 'listenerIdentifier': listener_id},
                    'items',
                    retry=getattr(resource_manager, 'retry', None),
                )
                or []
            )
            for rule in rules:
                rule['serviceIdentifier'] = service_id
                rule['listenerIdentifier'] = listener_id
            return rules

        if service_id:
            services = [{'id': service_id}]
        else:
            services = (
                self._invoke_client_enum(
                    client,
                    'list_services',
                    {},
                    'items',
                    retry=getattr(resource_manager, 'retry', None),
                )
                or []
            )

        results = []
        for service in services:
            current_service_id = service.get('id') or service.get('arn')
            if not current_service_id:
                continue
            listeners = (
                self._invoke_client_enum(
                    client,
                    'list_listeners',
                    {'serviceIdentifier': current_service_id},
                    'items',
                    retry=getattr(resource_manager, 'retry', None),
                )
                or []
            )
            for listener in listeners:
                current_listener_id = listener.get('id') or listener.get('arn')
                if not current_listener_id:
                    continue
                rules = (
                    self._invoke_client_enum(
                        client,
                        'list_rules',
                        {
                            'serviceIdentifier': current_service_id,
                            'listenerIdentifier': current_listener_id,
                        },
                        'items',
                        retry=getattr(resource_manager, 'retry', None),
                    )
                    or []
                )
                for rule in rules:
                    rule['serviceIdentifier'] = current_service_id
                    rule['listenerIdentifier'] = current_listener_id
                results.extend(rules)
        return results


class VPCLatticeRuleSource(DescribeWithResourceTags):
    resource_query_factory = VPCLatticeRuleQuery


@resources.register('vpc-lattice-rule')
class VPCLatticeRule(QueryResourceManager):
    """VPC Lattice Rule Resource"""

    source_mapping = {
        'describe': VPCLatticeRuleSource,
    }

    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_rules', 'items', None)
        arn = 'arn'
        id = 'id'
        name = 'name'
        universal_taggable = object()
        permissions_enum = (
            'vpc-lattice:ListRules',
            'vpc-lattice:ListListeners',
            'vpc-lattice:ListServices',
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
