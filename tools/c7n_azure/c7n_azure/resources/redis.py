# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.filters import ListItemFilter
from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


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
class RedisFirewallFilter(ListItemFilter):
    """
    Filter redis caches based on their firewall rules

    :example:

    This policy will find all the redis caches exposed to the public Internet

    .. code-block: yaml

        policies:
          - name: exposed-redis
            resource: azure.redis
            filters:
              - type: firewall
                attrs:
                  - type: value
                    key: properties.startIP
                    value: 0.0.0.0
                  - type: value
                    key: properties.endIP
                    value: 0.0.0.0

    """
    schema = type_schema(
        "firewall",
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"}
    )
    annotate_items = True
    item_annotation_key = "c7n:FirewallRules"

    def get_item_values(self, resource):
        client = self.manager.get_client()
        rules = client.firewall_rules.list_by_redis_resource(
            cache_name=resource["name"],
            resource_group_name=resource["resourceGroup"]
        )
        return [rule.serialize(True) for rule in rules]
