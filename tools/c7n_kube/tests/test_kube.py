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
