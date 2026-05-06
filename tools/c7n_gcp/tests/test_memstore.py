# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest
from pytest_terraform import terraform


class RedisInstanceTest(BaseTest):

    def test_redis_instance_query(self):
        project_id = self.project_id
        factory = self.replay_flight_data('test_redis_instance_list_query', project_id=project_id)
        p = self.load_policy(
            {'name': 'redis-instance-query',
             'resource': 'gcp.redis'},
            session_factory=factory)
        resources = p.run()

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'projects/cloud-custodian/locations/'
                                               'us-central1/instances/instance-test')

        assert p.resource_manager.get_urns(resources) == [
            f"gcp:redis:us-central1:{project_id}:instance/instance-test"
        ]


@terraform('redis_cluster')
def test_redis_cluster_query(test, redis_cluster):
    session_factory = test.replay_flight_data("redis-cluster-query")
    policy = test.load_policy(
        {"name": "redis-cluster-query", "resource": "gcp.redis-cluster"},
        session_factory=session_factory,
    )
    resources = policy.run()
    test.assertEqual(len(resources), 2)


@terraform('redis_cluster')
def test_redis_cluster_filter(test, redis_cluster):
    primary_cluster_name = redis_cluster["google_redis_cluster.c7n_redis_cluster_primary.id"]
    session_factory = test.replay_flight_data("redis-cluster-filter")
    policy = test.load_policy(
        {
            "name": "redis-cluster-filter-auth-mode",
            "resource": "gcp.redis-cluster",
            "filters": [
                {
                    "type": "value",
                    "key": "authorizationMode",
                    "value": "AUTH_MODE_IAM_AUTH",
                }
            ],
        },
        session_factory=session_factory,
    )
    resources = policy.run()
    test.assertEqual(len(resources), 1)
    test.assertEqual(
        resources[0]["name"],
        primary_cluster_name,
    )
