# Copyright 2017-2018 Capital One Services, LLC
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


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
                    {"type": "subnet", "key": "SubnetId", "value": "subnet-0544e30702e2e1ad4"},
                ],
                "actions": [{"type": "delete"}]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].get('ClusterId'), 'cluster-p67ybp4edfr')
        self.assertEqual(
            client.describe_clusters(Filters={'clusterIds': ['cluster-p67ybp4edfe']}).get(
                'Clusters'), [])
