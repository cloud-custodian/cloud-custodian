# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

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
