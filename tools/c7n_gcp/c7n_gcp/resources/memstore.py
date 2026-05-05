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


@resources.register("redis-cluster")
class RedisCluster(QueryResourceManager):
    """GCP resource:
    https://cloud.google.com/memorystore/docs/cluster/reference/rest/v1/projects.locations.clusters

    :example:

    .. code-block:: yaml

            policies:
              - name: gcp-memorystore-redis-cluster-auth-mode
                description: |
                  Find Redis clusters not using IAM auth
                resource: gcp.redis-cluster
                filters:
                  - type: value
                    key: authorizationMode
                    op: ne
                    value: AUTH_MODE_IAM_AUTH
    """

    class resource_type(TypeInfo):
        service = "redis"
        version = "v1"
        component = "projects.locations.clusters"
        enum_spec = ("list", "clusters[]", None)
        scope_key = "parent"
        scope_template = "projects/{}/locations/-"
        name = id = "name"
        permissions = ("redis.clusters.list",)
        default_report_fields = ["name", "state", "createTime"]
        asset_type = "redis.googleapis.com/Cluster"
        urn_component = "cluster"
        urn_id_segments = (-1,)
