import sys

from unittest.mock import MagicMock, call

from common_kube import KubeTest

import pytest


class TestKube(KubeTest):
    @pytest.mark.skipif(sys.platform == "win32", reason="Windows CI has issues running this test")
    def test_kube_cache(self):
        # Run once to create cache
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                "name": "namespace",
                "resource": "k8s.namespace",
            },
            session_factory=factory,
            cache=True,
        )
        resources = p.run()
        self.assertTrue(len(resources))

        # second run to ensure that the cache is being used
        p.resource_manager.log = MagicMock()

        resources = p.run()
        self.assertTrue(len(resources))

        calls = [
            call("Using cached c7n_kube.resources.core.namespace.Namespace: 5"),
            call("Filtered from 5 to 5 namespace"),
        ]
        p.resource_manager.log.debug.assert_has_calls(calls)

    def test_kube_cache_keyed_by_resource_type(self):
        # Two resource types sharing one cache must not be handed each other's
        # resources.
        pod = self.load_policy({"name": "pods", "resource": "k8s.pod"}, cache=True)
        deployment = self.load_policy(
            {"name": "deployments", "resource": "k8s.deployment"}, config=pod.options
        )
        for p, kind in ((pod, "Pod"), (deployment, "Deployment")):
            # Close each cache connection before the temp dir is removed, as
            # windows won't delete a file that is still open.
            self.addCleanup(p.resource_manager._cache.close)
            self.patch(
                p.resource_manager.source,
                "get_resources",
                lambda query, kind=kind: [{"kind": kind}],
            )

        self.assertEqual(pod.resource_manager.resources(), [{"kind": "Pod"}])
        self.assertEqual(deployment.resource_manager.resources(), [{"kind": "Deployment"}])
