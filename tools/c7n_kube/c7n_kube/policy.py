# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

from c7n.exceptions import PolicyValidationError
from c7n.policy import PolicyExecutionMode, execution
from c7n.utils import type_schema, dumps

from c7n_kube.exceptions import EventNotMatchedException, PolicyNotRunnableException

log = logging.getLogger("custodian.k8s.policy")


class K8sEventMode(PolicyExecutionMode):
    pass


@execution.register("k8s-admission")
class ValidatingControllerMode(K8sEventMode):
    """
    Validating Admission Controller Mode

    Actions are not compatible with Validating Admission Controller Mode

    Define operations to monitor:

    operations:
      - CREATE
      - UPDATE

    Include a description to provide a message on failure:

    .. example::

      policies:
        - name: 'require-only-label-foo'
          resource: 'k8s.deployment'
          description: 'All deployments must only have label:foo'
          mode:
            type: k8s-admission
            on-match: deny
            operations:
            - CREATE
          filters:
            - type: value
              key: keys(metadata.labels)
              value: ['foo']
              op: ne
    """

    schema = type_schema(
        "k8s-admission",
        required=["operations"],
        **{
            "subresource": {"type": "array", "items": {"type": "string"}},
            "on-match": {"enum": ["allow", "deny", "warn"]},
            "operations": {
                "type": "array",
                "items": {"enum": ["CREATE", "UPDATE", "DELETE", "CONNECT"]},
            },
        },
    )

    def validate(self):
        from c7n_kube.actions.core import EventAction

        actions = self.policy.resource_manager.actions
        errors = []
        for a in actions:
            if not isinstance(a, EventAction):
                errors.append(a.type)
        if errors:
            raise PolicyValidationError(
                f"Only Event Based actions are allowed: {errors} are not compatible"
            )

    def _handle_scope(self, request, value):
        if request.get("namespace") and value == "Namespaced":
            return True
        elif request.get("namespace") and value == "Cluster":
            return False
        elif not request.get("namespace") and value == "Cluster":
            return True
        return False

    def _handle_group(self, request, value):
        group = request["resource"]["group"]
        return group == value

    def _handle_resources(self, request, value):
        value = value[0]
        resource = request["resource"]["resource"]
        if len(value.split("/", 1)) == 2:
            parent, sub = value.split("/", 1)
            return sub == request["resourceSubResource"] and parent == resource
        return resource == value

    def _handle_api_versions(self, request, value):
        version = request["resource"]["version"]
        return version == value

    def _handle_operations(self, request, value):
        if "*" in value:
            return True
        return request["operation"] in value

    handlers = {
        "scope": _handle_scope,
        "group": _handle_group,
        "resources": _handle_resources,
        "apiVersions": _handle_api_versions,
        "operations": _handle_operations,
    }

    def get_match_values(self):
        scope = None
        version = None
        group = None
        resource = None

        subresources = self.policy.data.get("mode", {}).get("subresource", [])

        model = self.policy.resource_manager.get_model()
        mode = self.policy.data["mode"]

        # custom resources have to be treated a bit differently
        crds = (
            "custom-namespaced-resource",
            "custom-cluster-resource",
        )
        if self.policy.resource_manager.type in crds:
            query = self.policy.data["query"][0]
            version = query["version"].lower()
            group = query["group"].lower()
            resource = query["plural"].lower()
            scope = "Cluster"
            if self.policy.resource_manager.type == "custom-namespaced-resource":
                scope = "Namespaced"
        else:
            # set default values based on our models
            resource = model.plural.lower()
            group = model.canonical_group
            version = model.version.lower()
            scope = "Namespaced" if model.namespaced else "Cluster"

        resources = []

        resources.append(resource)

        if subresources:
            for s in subresources:
                resources.append(f"{resource}/{s}")

        return {
            "operations": mode.get("operations"),
            "resources": resources,
            "group": group,
            "apiVersions": version,
            "scope": scope,
        }

    def _filter_event(self, request):
        match_ = self.get_match_values()
        log.info(f"Matching event against:{match_}")
        matched = []
        for k, v in match_.items():
            if not v:
                continue
            matched.append(self.handlers[k](self, request, v))
        return all(matched)

    def run_resource_set(self, event, resources):
        with self.policy.ctx as ctx:
            ctx.metrics.put_metric(
                "ResourceCount", len(resources), "Count", Scope="Policy", buffer=False
            )

            if "debug" in event:
                self.policy.log.info("Invoking actions %s", self.policy.resource_manager.actions)

            ctx.output.write_file("resources.json", dumps(resources, indent=2))
            for action in self.policy.resource_manager.actions:
                self.policy.log.info(
                    "policy:%s invoking action:%s resources:%d",
                    self.policy.name,
                    action.name,
                    len(resources),
                )
                results = action.process(resources, event)
                ctx.output.write_file("action-%s" % action.name, dumps(results))
        return resources

    def run(self, event, _):
        if not self.policy.is_runnable(event):
            raise PolicyNotRunnableException()
        log.info(f"Got event:{event}")
        matched = self._filter_event(event["request"])
        if not matched:
            log.warning("Event not matched, skipping")
            raise EventNotMatchedException()
        log.info("Event Matched")

        resources = [event["request"]["object"]]
        # we want to inspect the thing getting deleted, not null
        if event["request"]["operation"] == "DELETE":
            resources = [event["request"]["oldObject"]]

        resources = self.policy.resource_manager.filter_resources(resources, event)
        resources = self.run_resource_set(event, resources)

        log.info(f"Filtered from 1 to {len(resources)} resource(s)")

        return resources
