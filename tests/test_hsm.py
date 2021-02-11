# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
import time


class CloudHSMClusterTest(BaseTest):

    def test_cloudhsm(self):
        factory = self.replay_flight_data("test_cloudhsm")
        client = factory().client("cloudhsmv2")
        p = self.load_policy(
            {
                "name": "cloudhsm",
                "resource": "cloudhsm-cluster",
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        id = resources[0]["ClusterId"]
        tags = client.list_tags(ResourceId=id)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertTrue("foo" in tag_map)

    def test_cloudhsm_subnet_delete(self):
        factory = self.replay_flight_data("test_cloudhsm_subnet_delete")
        client = factory().client("cloudhsmv2")
        p = self.load_policy(
            {
                "name": "cloudhsm",
                "resource": "cloudhsm-cluster",
                "filters": [
                    {"type": "subnet", "key": "SubnetId", "value": "subnet-914763e7"},
                ],
                "actions": [{"type": "delete"}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].get('ClusterId'), 'cluster-pqczsunscng')
        self.assertEqual(resources[0].get('SubnetMapping'), {"us-east-1a": "subnet-914763e7"})
        if self.recording:
            time.sleep(25)
        self.assertEqual(
            client.describe_clusters(Filters={'clusterIds': ['cluster-pqczsunscng']}).get(
                'Clusters')[0].get('State'), 'DELETED')

    def test_cloudhsm_tag(self):
        factory = self.replay_flight_data("test_cloudhsm_tag")
        client = factory().client("cloudhsmv2")
        p = self.load_policy(
            {
                "name": "cloudhsm",
                "resource": "cloudhsm-cluster",
                "filters": [{"tag:c7n": "absent"}],
                "actions": [{"type": "tag", "key": "c7n", "value": "test"}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        id = resources[0]["ClusterId"]
        tags = client.list_tags(ResourceId=id)
        tag_map = {t["Key"]: t["Value"] for t in tags["TagList"]}
        self.assertTrue("c7n" in tag_map)
