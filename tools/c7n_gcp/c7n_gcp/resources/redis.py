# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('redis-instance')
class RedisInstance(QueryResourceManager):
    """GC resource: https://cloud.google.com/memorystore/docs/redis/reference/rest

    :example:

    .. code-block:: yaml

            policies:
              - name: epam-gcp-memorystore_for_redis_auth
                description: |
                  GCP Memorystore for Redis has AUTH disabled
                resource: gcp.redis-instance
                filters:
                  - type: value
                    key: authEnabled
                    op: ne
                    value: true
    """
    class resource_type(TypeInfo):
        service = 'redis'
        version = 'v1'
        component = 'projects.locations.instances'
        enum_spec = ('list', 'instances[]', None)
        scope_key = 'parent'
        name = id = 'id'
        scope_template = "projects/{}/locations/-"
        permissions = ('bigtable.instances.list',)
        default_report_fields = ['displayName', 'expireTime']
