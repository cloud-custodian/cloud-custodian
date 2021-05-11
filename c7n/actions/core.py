# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Actions to take on resources
"""
import logging
import traceback

from c7n.element import Element
from c7n.exceptions import PolicyValidationError, ClientError
from c7n.registry import PluginRegistry


class ActionRegistry(PluginRegistry):

    def __init__(self, *args, **kw):
        super(ActionRegistry, self).__init__(*args, **kw)
        # Defer to provider initialization of registry
        from .webhook import Webhook
        self.register('webhook', Webhook)

    def parse(self, data, manager):
        results = []
        for d in data:
            results.append(self.factory(d, manager))
        return results

    def factory(self, data, manager):
        if isinstance(data, dict):
            action_type = data.get('type')
            if action_type is None:
                raise PolicyValidationError(
                    "Invalid action type found in %s" % (data))
        else:
            action_type = data
            data = {}

        action_class = self.get(action_type)
        if action_class is None:
            raise PolicyValidationError(
                "Invalid action type %s, valid actions %s" % (
                    action_type, list(self.keys())))
        # Construct a ResourceManager
        return action_class(data, manager)


class ActionResults:
    AnnotationKey = "c7n:Actions"
    allowed_states = ("ok", "skip", "error")

    def __init__(self, action):
        self.action = action
        self.details = None
        self.metrics = {i: 0 for i in self.allowed_states}
        self.resources = {}

    @property
    def id_key(self):
        return self.action.id_key

    def initialize(self, resources):
        if self.id_key:
            # if we're initializing and our model has an id key
            # then all resources should include it.
            self.resources = {r[self.id_key]: r for r in resources}

    def ok(self, resources):
        self._add(resources, status="ok")

    def skip(self, resources, reason):
        self._add(resources, status="skip", reason=reason)

    def error(self, resources, reason):
        self._add(resources, status="error", reason=reason)

    def set_details(self, details):
        self.details = details

    def remaining(self, status, reason=None):
        if status not in self.allowed_states:
            ValueError(
                "{} is not a valid state: {}".format(status, self.allowed_states)
            )
        # rely on the fact we can only record one status per resource
        self._add(list(self.resources), status=status, reason=reason)

    def _add(self, resources, status, reason=None):
        if isinstance(resources, (list, set, tuple)):
            for r in resources:
                self._set_status(r, status, reason)
        else:
            self._set_status(resources, status, reason)

    def _set_status(self, resource, status, reason=None):
        # if this resource doesn't support this, then
        # these are just big no-ops
        if not self.id_key:
            return

        if isinstance(resource, str):
            # support passing in just a resource id
            rid = resource
        else:
            # ... or a full resource
            rid = resource.get(self.id_key)

        # only support recording state once
        if not rid or rid not in self.resources:
            return

        r = self.resources[rid]

        # store something reasonable to serialize
        if isinstance(reason, Exception):
            reason = str(reason)

        record = {"action": self.action.name, "status": status, "reason": reason}
        self.metrics[status] += 1
        r[self.AnnotationKey] = r.get(self.AnnotationKey, []) + [record]
        # only record one result for a resource
        del self.resources[rid]

    def get_resource_status(self, resource):
        return resource.get(self.AnnotationKey, [])


class Action(Element):

    log = logging.getLogger("custodian.actions")

    def __init__(self, data=None, manager=None, log_dir=None):
        self.data = data or {}
        self.manager = manager
        self.log_dir = log_dir
        self.id_key = getattr(manager.get_model(), 'id', None) if manager else None
        self.results = ActionResults(self)

    @property
    def name(self):
        return self.__class__.__name__.lower()

    def wrap_process(self, resources, event=None):
        self.results.initialize(resources)
        resources, skipped = self.split_resources_by_results(resources)
        self.results.skip(skipped, "previously failed")
        try:
            if isinstance(self, EventAction):
                details = self.process(resources, event=event)
            else:
                details = self.process(resources)
            # no errors so anything left over is considered ok
            self.results.remaining("ok")
            self.results.set_details(details)
        except Exception as e:
            # remaining resources as errors
            self.results.remaining("error", e)
            self.results.set_details({"Exception": traceback.format_exc()})
            self.log.error("Error processing action:%s %s" % (self.name, traceback.format_exc()))
        return self.results

    # by default just split by success/failure
    def split_resources_by_results(self, resources, allowed_values=(), exclude=("error",)):
        return self.split_resources(
            resources,
            '"{}"[].status'.format(ActionResults.AnnotationKey),
            allowed_values=allowed_values,
            exclude=exclude,
        )

    def process(self, resources):
        raise NotImplementedError(
            "Base action class does not implement behavior")

    def _run_api(self, cmd, *args, **kw):
        try:
            return cmd(*args, **kw)
        except ClientError as e:
            if (e.response['Error']['Code'] == 'DryRunOperation' and
            e.response['ResponseMetadata']['HTTPStatusCode'] == 412 and
            'would have succeeded' in e.response['Error']['Message']):
                return self.log.info(
                    "Dry run operation %s succeeded" % (
                        self.__class__.__name__.lower()))
            raise


BaseAction = Action


class EventAction(BaseAction):
    """Actions which receive lambda event if present
    """
