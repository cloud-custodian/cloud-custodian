# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import copy

from c7n.actions import Action as BaseAction
from c7n.utils import local_session, chunks, type_schema
from c7n.exceptions import PolicyValidationError

from kubernetes.client import V1DeleteOptions

log = logging.getLogger("custodian.k8s.actions")


class Action(BaseAction):
    pass


class EventAction(BaseAction):
    def validate(self):
        modes = ("k8s-admission",)
        policy = self.manager.data
        if policy.get("mode", {}).get("type") not in modes:
            raise PolicyValidationError(
                "Event Actions are only supported for k8s-admission mode policies"
            )


class MethodAction(Action):
    method_spec = ()
    chunk_size = 20

    def validate(self):
        if not self.method_spec:
            raise NotImplementedError("subclass must define method_spec")
        return self

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        m = self.manager.get_model()
        client = session.client(m.group, m.version)
        for resource_set in chunks(resources, self.chunk_size):
            self.process_resource_set(client, resource_set)

    def process_resource_set(self, client, resources):
        op_name = self.method_spec["op"]
        op = getattr(client, op_name)
        for r in resources:
            op(name=r["metadata"]["name"])


class PatchAction(MethodAction):
    """
    Patches a resource

    Requires patch and namespaced attributes on the resource definition
    """

    def validate(self):
        if not self.manager.get_model().patch:
            raise PolicyValidationError("patch attribute not defined for resource")
        return self

    def get_permissions(self):
        patch = self.manager.get_model().patch
        return "".join([a.capitalize() for a in patch.split("_")])

    def patch_resources(self, client, resources, **patch_args):
        from kubernetes.client.exceptions import ApiException

        op = getattr(client, self.manager.get_model().patch)
        namespaced = self.manager.get_model().namespaced
        for r in resources:
            patch_args["name"] = r["metadata"]["name"]
            if namespaced:
                patch_args["namespace"] = r["metadata"]["namespace"]
            try:
                op(**patch_args)
            except ApiException as e:
                if e.status == 404:
                    log.warning(
                        f"Resource {r['metadata']['name']} not found - "
                        "it was likely deleted during execution"
                    )
                else:
                    raise

    def patch_resources_replicas(self, client, resources, patch):
        from kubernetes.client.exceptions import ApiException

        op = getattr(client, self.manager.get_model().patch)
        namespaced = self.manager.get_model().namespaced
        for r in resources:
            patch_args = patch[r['metadata']['name']]
            patch_args['name'] = r['metadata']['name']
            if namespaced:
                patch_args['namespace'] = r['metadata']['namespace']
            try:
                op(**patch_args)
            except ApiException as e:
                if e.status == 404:
                    log.warning(
                        f"Resource {r['metadata']['name']} not found - "
                        "it was likely deleted during execution"
                    )
                else:
                    raise


class PatchResource(PatchAction):
    """
    Patches a Kubernetes resource with enhanced capabilities

    Supports save/restore functionality for off-hours resource management
    and improved error handling for production environments.

    .. code-block:: yaml

      policies:
        # Basic patching - scale deployment to 0 replicas
        - name: scale-down-deployment
          resource: k8s.deployment
          filters:
            - 'metadata.name': 'my-app'
          actions:
            - type: patch
              options:
                spec:
                  replicas: 0

        # Save current replica count before scaling down (off-hours scaling)
        - name: offhours-scale-down
          resource: k8s.deployment
          filters:
            - 'metadata.name': 'my-app'
            - type: value
              key: 'spec.replicas'
              op: gt
              value: 0
          actions:
            - type: patch
              save-options-tag: "custodian-original-replicas"
              options:
                spec:
                  replicas: 0

        # Restore original replica count (business hours scaling)
        - name: business-hours-scale-up
          resource: k8s.deployment
          filters:
            - 'metadata.name': 'my-app'
            - 'metadata.labels.custodian-original-replicas': present
          actions:
            - type: patch
              restore-options-tag: "custodian-original-replicas"

        # Complex patching with multiple changes
        - name: update-deployment-config
          resource: k8s.deployment
          filters:
            - 'metadata.name': 'my-app'
          actions:
            - type: patch
              options:
                spec:
                  replicas: 3
                  template:
                    metadata:
                      labels:
                        version: "v2.1"
                    spec:
                      containers:
                        - name: app
                          resources:
                            requests:
                              memory: "256Mi"
                              cpu: "100m"
    """

    schema = type_schema(
        'patch',
        **{
            'options': {'type': 'object'},
            'save-options-tag': {'type': 'string'},
            'restore-options-tag': {'type': 'string'},
        },
    )

    def process_resource_set(self, client, resources):

        patch = {}

        for r in resources:
            patch_args = copy.deepcopy({'body': self.data.get('options', {})})

            if 'save-options-tag' in self.data:
                save_tag = self.data.get('save-options-tag', {})
                replicas = r['spec']['replicas']
                if not r['metadata']['labels']:
                    r['metadata']['labels'] = {}
                r['metadata']['labels'][save_tag] = f'replicas-{replicas}'
                patch_args['body']['metadata'] = {}
                patch_args['body']['metadata']['labels'] = r['metadata']['labels']
                patch[r['metadata']['name']] = patch_args
            elif 'restore-options-tag' in self.data:
                restore_tag = self.data.get('restore-options-tag', {})

                if restore_tag in r['metadata']['labels']:
                    replicas = r['metadata']['labels'][restore_tag].split('-')[1]
                    patch_args['body']['spec'] = {'replicas': int(replicas)}

            patch[r['metadata']['name']] = patch_args

        self.patch_resources_replicas(client, resources, patch)

    @classmethod
    def register_resources(klass, registry, resource_class):
        model = resource_class.resource_type
        if hasattr(model, "patch") and hasattr(model, "namespaced"):
            resource_class.action_registry.register("patch", klass)


class DeleteAction(MethodAction):
    """
    Deletes a resource

    Requires delete and namespaced attributes on the resource definition
    """

    def validate(self):
        if not self.manager.get_model().delete:
            raise PolicyValidationError("delete attribute not defined for resource")
        return self

    def get_permissions(self):
        delete = self.manager.get_model().delete
        return "".join([a.capitalize() for a in delete.split("_")])

    def delete_resources(self, client, resources, **delete_args):
        op = getattr(client, self.manager.get_model().delete)
        namespaced = self.manager.get_model().namespaced
        for r in resources:
            delete_args["name"] = r["metadata"]["name"]
            if namespaced:
                delete_args["namespace"] = r["metadata"]["namespace"]
            op(**delete_args)


class DeleteResource(DeleteAction):
    """
    Deletes a Resource

    .. code-block:: yaml
      policies:
        - name: delete-resource
          resource: k8s.pod # k8s.{resource}
          filters:
            - 'metadata.name': 'test-{resource}'
          actions:
            - delete
    """

    schema = type_schema(
        "delete",
        grace_period_seconds={"type": "integer"},
    )

    def process_resource_set(self, client, resources):
        grace = self.data.get("grace_period_seconds", 30)
        body = V1DeleteOptions()
        body.grace_period_seconds = grace
        delete_args = {"body": body}
        self.delete_resources(client, resources, **delete_args)

    @classmethod
    def register_resources(klass, registry, resource_class):
        model = resource_class.resource_type
        if (
            "delete" not in resource_class.action_registry
            and hasattr(model, "delete")
            and hasattr(model, "namespaced")
        ):
            resource_class.action_registry.register("delete", klass)
