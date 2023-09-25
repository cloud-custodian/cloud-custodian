# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import copy
import logging

import jsonpatch

from c7n_kube.actions.core import PatchAction, EventAction
from c7n.utils import type_schema

log = logging.getLogger("custodian.k8s.labels")


class LabelAction(PatchAction):
    """
    Labels a resource

    .. code-block:: yaml

      policies:
        - name: label-resource
          resource: k8s.pod # k8s.{resource}
          filters:
            - 'metadata.name': 'name'
          actions:
            - type: label
              labels:
                label1: value1
                label2: value2

    To remove a label from a resource, provide the label with the value ``null``

    .. code-block:: yaml

      policies:
        - name: remove-label-from-resource
          resource: k8s.pod # k8s.{resource}
          filters:
            - 'metadata.labels.label1': present
          actions:
            - type: label
              labels:
                label1: null

    """

    schema = type_schema("label", labels={"type": "object"})

    def process_resource_set(self, client, resources):
        body = {"metadata": {"labels": self.data.get("labels", {})}}
        patch_args = {"body": body}
        self.patch_resources(client, resources, **patch_args)

    @classmethod
    def register_resources(klass, registry, resource_class):
        model = resource_class.resource_type
        if hasattr(model, "patch") and hasattr(model, "namespaced"):
            resource_class.action_registry.register("label", klass)


class EventLabelAction(EventAction):
    """
    Label a resource on event

    .. code-block:: yaml

        policies:
          - name: 'label-foo-on-creation'
            resource: 'k8s.deployment'
            mode:
              type: k8s-admission
              on-match: allow
              operations:
                - CREATE
            actions:
              - type: event-label
                labels:
                  foo: bar
    """

    schema = type_schema("event-label", labels={"type": "object"}, required=["labels"])

    def get_labels(self, event):
        return self.data["labels"]

    def process_labels(self, resource, labels):
        remove = []
        for k, v in labels.items():
            if v is None:
                remove.append(k)
        resource.setdefault("c7n:patches", [])
        src = copy.deepcopy(resource)
        dst = copy.deepcopy(src)
        # if the key doesnt exist we need to set it else it wont appear
        # in the patch
        if dst.get("metadata", {}).get("labels") is None:
            dst["metadata"]["labels"] = labels
        else:
            dst.get("metadata", {}).get("labels", {}).update(labels)
        for r in remove:
            if r in dst.get("metadata", {}).get("labels", {}):
                dst.get("metadata", {}).get("labels", {}).pop(r)
        patch = jsonpatch.make_patch(src, dst)
        resource["c7n:patches"].extend(patch.patch)

    def process(self, resources, event):
        for r in resources:
            labels = self.get_labels(event)
            self.process_labels(r, labels)

    @classmethod
    def register_resources(klass, registry, resource_class):
        resource_class.action_registry.register("event-label", klass)


class AutoLabelUser(EventLabelAction):
    """
    Label the user that triggered the event

    Default label key is OwnerContact, set 'key' to specify a different one

    .. code-block:: yaml

        policies:
          - name: 'auto-label-creator'
            resource: 'k8s.deployment'
            mode:
              type: k8s-admission
              on-match: allow
              operations:
                - CREATE
            actions:
              - type: auto-label-user
                key: owner
    """

    schema = type_schema("auto-label-user", key={"type": "string"})

    def get_labels(self, event):
        label_key = self.data.get("key", "OwnerContact")
        event_owner = event["request"]["userInfo"]["username"]
        return {label_key: event_owner}

    @classmethod
    def register_resources(klass, registry, resource_class):
        resource_class.action_registry.register("auto-label-user", klass)
