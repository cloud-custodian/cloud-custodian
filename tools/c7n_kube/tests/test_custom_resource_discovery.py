# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock, patch

from common_kube import KubeTest

from c7n_kube.resources.custom_resource import CustomResource, tag_custom_resource_instance


class TestTagCustomResourceInstance(KubeTest):
    """Pure function -- no live cluster, no cassette needed."""

    def test_injects_crd_identity_without_touching_wire_content(self):
        raw = {
            "apiVersion": "karpenter.sh/v1",
            "kind": "NodePool",
            "metadata": {"name": "general-purpose", "uid": "abc-123"},
            "spec": {"weight": 1},
        }
        tagged = tag_custom_resource_instance(
            raw, group="karpenter.sh", version="v1", plural="nodepools", scope="Cluster"
        )
        # Real wire content untouched.
        self.assertEqual(tagged["kind"], "NodePool")
        self.assertEqual(tagged["metadata"], raw["metadata"])
        self.assertEqual(tagged["spec"], raw["spec"])
        # Injected identity fields present.
        self.assertEqual(tagged["crd_group"], "karpenter.sh")
        self.assertEqual(tagged["crd_version"], "v1")
        self.assertEqual(tagged["crd_plural"], "nodepools")
        self.assertEqual(tagged["crd_scope"], "Cluster")

    def test_does_not_mutate_the_input_dict(self):
        raw = {"kind": "NodePool", "metadata": {}, "spec": {}}
        tag_custom_resource_instance(
            raw, group="karpenter.sh", version="v1", plural="nodepools", scope="Cluster"
        )
        self.assertNotIn("crd_group", raw)


class TestCustomResourceDiscovery(KubeTest):
    def test_resources_discovers_and_tags_real_crd_instances(self):
        # Recorded against a real kube-apiserver with the real Karpenter
        # NodePool CRD installed and one real instance created -- discovery
        # (ApiextensionsV1Api.list_custom_resource_definition, a typed call)
        # plus instance listing (list_cluster_custom_object, a raw-dict
        # call), exactly the two-call sequence _discover_crds/_list_instances
        # perform.
        factory = self.replay_flight_data()
        p = self.load_policy(
            {"name": "cr", "resource": "k8s.custom-resource"},
            session_factory=factory,
        )
        resources = p.resource_manager.resources()
        self.assertEqual(len(resources), 1)
        r = resources[0]
        self.assertEqual(r["kind"], "NodePool")
        self.assertEqual(r["crd_group"], "karpenter.sh")
        self.assertEqual(r["crd_version"], "v1")
        self.assertEqual(r["crd_plural"], "nodepools")
        self.assertEqual(r["crd_scope"], "Cluster")
        self.assertEqual(r["metadata"]["name"], "general-purpose")
        # Real server-populated fields, not a submitted manifest.
        self.assertTrue(r["metadata"]["uid"])
        self.assertTrue(r["metadata"]["resourceVersion"])


class TestCustomResourceFilterResourcesPreserved(KubeTest):
    """filter_resources() must run on the aggregated stream -- confirmed by
    a policy filters: block actually excluding a matching instance, not
    silently no-opping (the round-1 review finding this guards against)."""

    def test_filters_block_excludes_matching_instance(self):
        real_manager = self._build_manager_with_filter()
        real_manager._discover_crds = MagicMock(
            return_value=[
                {
                    "kind": "NodePool",
                    "group": "karpenter.sh",
                    "version": "v1",
                    "plural": "nodepools",
                    "scope": "Cluster",
                }
            ]
        )
        real_manager._list_instances = MagicMock(
            return_value=[
                {
                    "kind": "NodePool",
                    "crd_group": "karpenter.sh",
                    "metadata": {"name": "keep-me"},
                },
                {
                    "kind": "NodePool",
                    "crd_group": "karpenter.sh",
                    "metadata": {"name": "exclude-me"},
                },
            ]
        )
        resources = real_manager.resources()
        names = [r["metadata"]["name"] for r in resources]
        self.assertEqual(names, ["keep-me"])

    def _build_manager_with_filter(self):
        # No real network call is made in this test (both discovery and
        # listing are mocked below), so no cassette/live session is needed --
        # a plain MagicMock session_factory is enough to construct the policy.
        p = self.load_policy(
            {
                "name": "cr",
                "resource": "k8s.custom-resource",
                "filters": [
                    {"type": "value", "key": "metadata.name", "value": "exclude-me", "op": "ne"}
                ],
            },
            session_factory=lambda: MagicMock(),
        )
        return p.resource_manager


class TestDiscoverCrdsVersionSelection(KubeTest):
    """_discover_crds must pick the storage version among multiple served
    versions, and skip (with a log) a CRD whose storage version isn't
    currently served -- the round-1 review finding this guards against."""

    def _build_manager(self):
        p = self.load_policy(
            {"name": "cr", "resource": "k8s.custom-resource"},
            session_factory=lambda: MagicMock(),
        )
        return p.resource_manager

    def _fake_crd_version(self, name, *, storage, served):
        v = MagicMock()
        v.name = name
        v.storage = storage
        v.served = served
        return v

    def _fake_crd(self, *, kind, group, plural, scope, versions):
        crd = MagicMock()
        crd.spec.names.kind = kind
        crd.spec.names.plural = plural
        crd.spec.group = group
        crd.spec.scope = scope
        crd.spec.versions = versions
        return crd

    def test_selects_storage_version_among_multiple_served_versions(self):
        manager = self._build_manager()
        session = MagicMock()
        crd = self._fake_crd(
            kind="Widget",
            group="example.com",
            plural="widgets",
            scope="Cluster",
            versions=[
                self._fake_crd_version("v1beta1", storage=False, served=True),
                self._fake_crd_version("v1", storage=True, served=True),
            ],
        )
        session.client.return_value.list_custom_resource_definition.return_value.items = [crd]
        discovered = list(manager._discover_crds(session))
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["version"], "v1")

    def test_skips_crd_whose_storage_version_is_not_served(self):
        manager = self._build_manager()
        session = MagicMock()
        crd = self._fake_crd(
            kind="Widget",
            group="example.com",
            plural="widgets",
            scope="Cluster",
            versions=[self._fake_crd_version("v1", storage=True, served=False)],
        )
        session.client.return_value.list_custom_resource_definition.return_value.items = [crd]
        with self.assertLogs("custodian.k8s.custom_resource", level="WARNING") as logs:
            discovered = list(manager._discover_crds(session))
        self.assertEqual(discovered, [])
        self.assertTrue(any("widgets" in msg for msg in logs.output))


class TestListInstancesNamespacedPath(KubeTest):
    """_list_instances must use the all-namespaces enum op (with
    resource_plural, not plural) for a Namespaced-scope CRD, and must not
    strip a raw instance's own real `kind` field along the way -- the
    round-1 review finding this guards against (only the Cluster-scoped
    path had cassette coverage before)."""

    def test_namespaced_crd_uses_correct_enum_op_and_preserves_kind(self):
        manager = self.load_policy(
            {"name": "cr", "resource": "k8s.custom-resource"},
            session_factory=lambda: MagicMock(),
        ).resource_manager
        crd = {
            "kind": "Addon",
            "group": "k3s.cattle.io",
            "version": "v1",
            "plural": "addons",
            "scope": "Namespaced",
        }
        raw_item = {"kind": "Addon", "metadata": {"name": "ccm", "namespace": "kube-system"}}
        with patch(
            "c7n_kube.resources.custom_resource.ResourceQuery._invoke_client_enum",
            return_value=[raw_item],
        ) as mock_enum:
            tagged = manager._list_instances(MagicMock(), crd)
        enum_op, params = mock_enum.call_args.args[1], mock_enum.call_args.args[2]
        self.assertEqual(enum_op, "list_custom_object_for_all_namespaces")
        self.assertIn("resource_plural", params)
        self.assertNotIn("plural", params)
        self.assertEqual(tagged[0]["kind"], "Addon")
        self.assertEqual(tagged[0]["crd_scope"], "Namespaced")


class TestCustomResourceCanonicalGroup(KubeTest):
    def test_service_is_not_mislabeled_as_core(self):
        self.assertEqual(CustomResource.resource_type.canonical_group, "custom-resource")


class TestCustomResourceOneCrdFailureIsolation(KubeTest):
    def test_one_crd_listing_failure_does_not_abort_others(self):
        # No real network call is made (both discovery and listing are
        # mocked below), so a plain MagicMock session_factory is enough.
        p = self.load_policy(
            {"name": "cr", "resource": "k8s.custom-resource"},
            session_factory=lambda: MagicMock(),
        )
        manager = p.resource_manager
        manager._discover_crds = MagicMock(
            return_value=[
                {
                    "kind": "Broken",
                    "group": "broken.example.com",
                    "version": "v1",
                    "plural": "brokens",
                    "scope": "Cluster",
                },
                {
                    "kind": "Working",
                    "group": "working.example.com",
                    "version": "v1",
                    "plural": "workings",
                    "scope": "Cluster",
                },
            ]
        )

        def fake_list_instances(session, crd):
            if crd["kind"] == "Broken":
                raise RuntimeError("simulated RBAC denial")
            return [{"kind": "Working", "metadata": {"name": "still-here"}}]

        manager._list_instances = fake_list_instances
        resources = manager.resources()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["metadata"]["name"], "still-here")
