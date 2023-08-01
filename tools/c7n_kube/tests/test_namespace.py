# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
from common_kube import KubeTest


class NamespaceTest(KubeTest):
    def test_ns_query(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {"name": "all-namespaces", "resource": "k8s.namespace"},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        self.assertEqual(
            sorted([r["metadata"]["name"] for r in resources]),
            ["default", "kube-public", "kube-system"],
        )

    def test_ns_delete(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "del-ns",
                "resource": "k8s.namespace",
                "filters": [{"metadata.name": "hello"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["metadata"]["name"], "hello")
        self.assertEqual(resources[0]["status"]["phase"], "Active")

        if self.recording:
            time.sleep(1)

        client = factory().client("Core", "V1")
        response = client.read_namespace("hello")
        self.assertEqual(response.status.phase, "Terminating")
