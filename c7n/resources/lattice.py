# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import re

from c7n.filters import ValueFilter
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import (
    ChildDescribeSource,
    ChildResourceManager,
    ChildResourceQuery,
    DescribeWithResourceTags,
    QueryResourceManager,
    sources,
    TypeInfo,
)
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema

log = logging.getLogger('custodian.lattice')


@resources.register('vpc-lattice-service-network')
class VPCLatticeServiceNetwork(QueryResourceManager):
    """VPC Lattice Service Network Resource"""

    source_mapping = {
        'describe': DescribeWithResourceTags,
    }

    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_service_networks', 'items', None)
        detail_spec = ('get_service_network', 'serviceNetworkIdentifier', 'id', None)
        arn = 'arn'
        id = 'id'
        name = 'name'
        universal_taggable = object()
        permissions_enum = ('vpc-lattice:ListServiceNetworks',)
        permissions_augment = ('vpc-lattice:GetServiceNetwork', 'vpc-lattice:ListTagsForResource',)


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


class DescribeVPCLatticeListener(ChildDescribeSource):
    def augment(self, resources):
        return universal_augment(self.manager, resources)


@resources.register('vpc-lattice-listener')
class VPCLatticeListener(ChildResourceManager):
    """VPC Lattice listener resource.

    :example:

    .. code-block:: yaml

        policies:
          - name: lattice-listener-http
            resource: aws.vpc-lattice-listener
            filters:
              - type: value
                key: protocol
                value: HTTP
    """

    source_mapping = {
        'describe-child': DescribeVPCLatticeListener,
    }

    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_listeners', 'items', None)
        parent_spec = ('vpc-lattice-service', 'serviceIdentifier', True)
        arn = 'arn'
        id = 'id'
        name = 'name'
        universal_taggable = object()
        permissions_enum = ('vpc-lattice:ListListeners',)


class VPCLatticeRuleQuery(ChildResourceQuery):
    def _list_listeners(self, service_id=None):
        listener_manager = self.manager.get_resource_manager('vpc-lattice-listener')

        # If service is specified, only get listeners for that service.
        if service_id:
            query = {'serviceIdentifier': service_id}
            listeners = listener_manager.resources(query, augment=False)
            return [{**l, **query} for l in listeners]

        # Otherwise, get all listeners and parse the service id from the arn.
        listeners = []
        for l in listener_manager.resources(augment=False):
            match = re.search(r":service/(svc-[^/]+)/listener/", l['arn'])
            service_id = match.group(1) if match else None
            listeners.append({**l, 'serviceIdentifier': service_id})
        return listeners

    def filter(self, resource_manager, parent_ids=None, **params):
        if parent_ids:
            raise ValueError(
                'This query is dependent on more than one ancestor id, so do not pass parent_ids.'
            )

        m = self.resolve(resource_manager.resource_type)
        client = local_session(self.session_factory).client(m.service)
        enum_op, path, extra_args = m.enum_spec

        def list_rules(service_id, listener_id):
            ids = {'serviceIdentifier': service_id, 'listenerIdentifier': listener_id}
            rules = self._invoke_client_enum(
                client,
                enum_op,
                {**params, **(extra_args or {}), **ids},
                path,
                retry=self.manager.retry
            )
            return [{**r, **ids} for r in rules]  # Augment rules with service and listener ids

        service_id = params.get('serviceIdentifier')
        listener_id = params.get('listenerIdentifier')
        if service_id and listener_id:
            # Query the rules directly
            rules = list_rules(service_id, listener_id)
        else:
            # Query listeners and then rules
            if listener_id:
                raise ValueError(
                    'Do not pass listenerIdentifier without serviceIdentifier in the query block.'
                    ' Either pass serviceIdentifier too or use listenerIdentifier as a filter.'
                )
            listeners = self._list_listeners(service_id)
            rules = []
            for l in listeners:
                rules.extend(list_rules(l['serviceIdentifier'], l['id']))
        return rules


@sources.register('vpc-lattice-rule')
class VPCLatticeRuleSource(ChildDescribeSource):
    resource_query_factory = VPCLatticeRuleQuery

    def augment(self, resources):
        return universal_augment(self.manager, resources)

    def get_query_params(self, query):
        """Pass serviceIdentifier and listenerIdentifier through to `filter`"""
        supported = ('serviceIdentifier', 'listenerIdentifier')
        query = query or {}
        for q in self.manager.data.get('query', []):
            for k in q:
                if k in supported:
                    query[k] = q[k]
                else:
                    log.warning(f'"{k}" is not a supported query parameter for this resource.')
        return query


@resources.register('vpc-lattice-rule')
class VPCLatticeRule(ChildResourceManager):
    """VPC Lattice listener rule resource.

    Rules are enumerated through listeners and require both
    ``serviceIdentifier`` and ``listenerIdentifier`` for direct API queries.
    This resource supports a custom ``query`` block with those keys to narrow
    enumeration before filters are applied.

    If only ``serviceIdentifier`` is provided in the query, Custodian will
    enumerate listeners for that service and then list rules for each listener.
    If both identifiers are provided, Custodian queries the rule API directly.
    A query with ``listenerIdentifier`` alone is rejected because the VPC
    Lattice API also requires the parent service identifier.

    :example:

    .. code-block:: yaml

        policies:
          - name: lattice-rule-by-service
            resource: aws.vpc-lattice-rule
            query:
              - serviceIdentifier: svc-0123456789abcdef0
            filters:
              - isDefault: false

          - name: lattice-rule-by-service-and-listener
            resource: aws.vpc-lattice-rule
            query:
              - serviceIdentifier: svc-0123456789abcdef0
              - listenerIdentifier: listener-0123456789abcdef0
            filters:
              - type: value
                key: priority
                value: 10
    """

    child_source = 'vpc-lattice-rule'
    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_rules', 'items', None)
        parent_spec = ('vpc-lattice-listener', 'listenerIdentifier', True)
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


class DescribeServiceNetworkAssociation(ChildDescribeSource):
    def augment(self, resources):
        return universal_augment(self.manager, resources)


@resources.register('vpc-lattice-service-network-association')
class VPCLatticeServiceNetworkAssociation(ChildResourceManager):
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
        'describe-child': DescribeServiceNetworkAssociation,
    }

    class resource_type(TypeInfo):
        service = 'vpc-lattice'
        enum_spec = ('list_service_network_vpc_associations', 'items', None)
        parent_spec = ('vpc-lattice-service-network', 'serviceNetworkIdentifier', True)
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
