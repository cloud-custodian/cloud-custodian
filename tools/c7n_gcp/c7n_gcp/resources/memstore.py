# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register("redis")
class RedisInstance(QueryResourceManager):
    """GC resource: https://cloud.google.com/memorystore/docs/redis/reference/rest

    :example:

    .. code-block:: yaml

            policies:
              - name: gcp-memorystore_for_redis_auth
                description: |
                  GCP Memorystore for Redis has AUTH disabled
                resource: gcp.redis
                filters:
                  - type: value
                    key: authEnabled
                    op: ne
                    value: true
    """

    class resource_type(TypeInfo):
        service = "redis"
        version = "v1"
        component = "projects.locations.instances"
        enum_spec = ("list", "instances[]", None)
        scope_key = "parent"
        name = id = "name"
        scope_template = "projects/{}/locations/-"
        permissions = ("bigtable.instances.list",)
        default_report_fields = ["displayName", "expireTime"]
        asset_type = "redis.googleapis.com/Instance"
        urn_component = "instance"
        urn_id_segments = (-1,)

        @classmethod
        def _get_location(cls, resource):
            return resource["name"].split("/")[3]
