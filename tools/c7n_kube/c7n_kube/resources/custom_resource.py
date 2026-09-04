# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n.utils import local_session

from c7n_kube.provider import resources
from c7n_kube.query import QueryMeta, QueryResourceManager, ResourceQuery, TypeInfo

log = logging.getLogger("custodian.k8s.custom_resource")


def tag_custom_resource_instance(raw_instance, *, group, version, plural, scope):
    """Tag a raw CRD instance dict with the identity of the CRD it came from.

    `kind` is deliberately not injected: every CustomObjectsApi list item
    already carries its own real `kind` on the wire, unlike
    group/version/plural/scope.
    """
    tagged = dict(raw_instance)
    tagged["crd_group"] = group
    tagged["crd_version"] = version
    tagged["crd_plural"] = plural
    tagged["crd_scope"] = scope
    return tagged


class CustomResourceTypeInfo(TypeInfo):
    # Resolves session.client("CustomObjects", "") -> CustomObjectsApi. Not
    # this type's own group/version -- there are many, one per discovered
    # CRD, decided at sync time.
    group = "CustomObjects"
    version = ""
    canonical_group = "custom-resource"


@resources.register("custom-resource")
class CustomResource(QueryResourceManager, metaclass=QueryMeta):
    """Discovers every installed CustomResourceDefinition (served, storage
    version only -- see _discover_crds), then lists instances of each,
    landing them all under this single resource type regardless of kind.

    `resources()` is fully overridden rather than relying on
    QueryResourceManager's default, since there's no single static
    group/version/plural for this type. `filter_resources()` is still
    called explicitly below -- dropping it would silently no-op any
    `filters:` block against this type.
    """

    class resource_type(CustomResourceTypeInfo):
        pass

    def resources(self, query=None):
        session = local_session(self.session_factory)
        instances = []
        for crd in self._discover_crds(session):
            try:
                instances.extend(self._list_instances(session, crd))
            except Exception:
                log.exception(
                    "failed to list instances of CRD %s/%s %s (group=%s); "
                    "continuing with other discovered CRDs",
                    crd["plural"],
                    crd["version"],
                    crd["kind"],
                    crd["group"],
                )
        return self.filter_resources(instances)

    def _discover_crds(self, session):
        """List installed CustomResourceDefinitions, yielding only those
        with a served, storage version. A CRD can serve multiple versions
        simultaneously with potentially divergent schemas; instances are
        listed under the storage version only, since it's the one
        guaranteed to exist and be authoritative.
        """
        client = session.client("Apiextensions", "V1")
        for crd in client.list_custom_resource_definition().items:
            storage_version = next((v for v in crd.spec.versions if v.storage), None)
            if storage_version is None or not storage_version.served:
                log.warning(
                    "skipping CRD %s/%s (group=%s): no served storage version -- "
                    "instances of this CRD will not appear until one exists",
                    crd.spec.names.plural,
                    crd.spec.names.kind,
                    crd.spec.group,
                )
                continue
            yield {
                "kind": crd.spec.names.kind,
                "group": crd.spec.group,
                "version": storage_version.name,
                "plural": crd.spec.names.plural,
                "scope": crd.spec.scope,
            }

    # Kubernetes list APIs only paginate when a caller opts in via `limit` --
    # a CRD like ArgoCD's Application can have thousands of instances, so
    # pass a page size explicitly rather than making one large unpaginated
    # call.
    page_size = 250

    def _list_instances(self, session, crd):
        client = session.client("CustomObjects", "")
        if crd["scope"] == "Cluster":
            enum_op = "list_cluster_custom_object"
            params = {
                "group": crd["group"],
                "version": crd["version"],
                "plural": crd["plural"],
                "limit": self.page_size,
            }
        else:
            # list_namespaced_custom_object needs a specific namespace,
            # which this account/cluster-wide sync doesn't have.
            enum_op = "list_custom_object_for_all_namespaces"
            params = {
                "group": crd["group"],
                "version": crd["version"],
                "resource_plural": crd["plural"],
                "limit": self.page_size,
            }
        raw_items = ResourceQuery(self.session_factory)._invoke_client_enum(
            client, enum_op, params, "items"
        )
        return [
            tag_custom_resource_instance(
                item,
                group=crd["group"],
                version=crd["version"],
                plural=crd["plural"],
                scope=crd["scope"],
            )
            for item in raw_items
        ]
