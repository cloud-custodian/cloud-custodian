# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n.filters import ValueFilter
from c7n.utils import type_schema
from c7n.filters.core import op


@resources.register('redis')
class Redis(ArmResourceManager):
    """Redis Resource

    :example:

    This policy will find all Redis caches with more than 1000 cache misses in the last 72 hours

    .. code-block:: yaml

        policies:
          - name: redis-cache-misses
            resource: azure.redis
            filters:
              - type: metric
                metric: cachemisses
                op: ge
                aggregation: count
                threshold: 1000
                timeframe: 72

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Databases']

        service = 'azure.mgmt.redis'
        client = 'RedisManagementClient'
        enum_spec = ('redis', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.redisVersion',
            'properties.sku.[name, family, capacity]'
        )
        resource_type = 'Microsoft.Cache/Redis'


@Redis.filter_registry.register('firewall')
class RedisFirewallFilter(ValueFilter):
    schema = type_schema('firewall', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        accepted = []
        client = self.manager.get_client('azure.mgmt.redis.RedisManagementClient')
        for resource in resources:
            firewall_rules = list(
                client.firewall_rules.list_by_redis_resource(
                    cache_name=resource['name'],
                    resource_group_name=resource['resourceGroup']))
            any_of = []
            for rule in firewall_rules:
                key = getattr(rule, self.data.get('key'))
                if key and op(self.data, key, self.data.get('value')):
                    any_of.append(True)
            if any(any_of):
                accepted.append(resource)

        return accepted
