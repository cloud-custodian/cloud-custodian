# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from gcp_common import BaseTest


class RedisInstanceTest(BaseTest):

    def test_redis_instance_query(self):
        project_id = 'gcp-lab-custodian'
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
            "gcp:redis:us-central1:gcp-lab-custodian:instance/instance-test"
        ]
