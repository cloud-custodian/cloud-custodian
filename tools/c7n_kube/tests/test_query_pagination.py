# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock

from common_kube import KubeTest

from c7n.exceptions import PolicyExecutionError
from c7n_kube.query import ResourceQuery


class TestQueryPagination(KubeTest):
    def test_pagination_multi_page(self):
        # Recorded against a real kube-apiserver seeded with 6 ConfigMaps,
        # queried with limit=2 (3 pages: 2, 2, 2 items).
        factory = self.replay_flight_data()
        p = self.load_policy(
            {"name": "config-maps", "resource": "k8s.config-map"},
            session_factory=factory,
        )
        manager = p.resource_manager
        query = ResourceQuery(manager.session_factory)
        resources = query.filter(manager, limit=2)
        self.assertEqual(len(resources), 6)

    def test_pagination_shape_change_raises(self):
        first_page = {
            "metadata": {"_continue": "token"},
            "items": [{"metadata": {"name": "a"}}],
        }
        second_page = {"metadata": {}}

        client = MagicMock()
        client.list_config_map_for_all_namespaces.side_effect = [first_page, second_page]

        query = ResourceQuery(session_factory=None)
        with self.assertRaises(PolicyExecutionError) as ctx:
            query._invoke_client_enum(
                client, "list_config_map_for_all_namespaces", {"limit": 2}, "items"
            )
        self.assertIn("1 item(s)", str(ctx.exception))
        self.assertIn("'items'", str(ctx.exception))
