# Copyright 2015-2017 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Actions to take on resources
"""
import logging
import traceback
from concurrent.futures import as_completed

from c7n.element import Element, split_resources
from c7n.exceptions import PolicyValidationError, ClientError
from c7n.executor import ThreadPoolExecutor
from c7n.registry import PluginRegistry
from c7n import utils


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
                raise PolicyValidationError("Invalid action type found in %s" % (data))
        else:
            action_type = data
            data = {}

        action_class = self.get(action_type)
        if action_class is None:
            raise PolicyValidationError(
                "Invalid action type %s, valid actions %s"
                % (action_type, list(self.keys()))
            )
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
        if isinstance(resources, list):
            for r in resources:
                self._set_status(r, status, reason)
        else:
            self._set_status(resources, status, reason)

    def _set_status(self, resource, status, reason=None):
        if isinstance(resource, str):
            # support passing in just a resource id
            rid = resource
        else:
            # ... or a full resource
            rid = resource[self.id_key]

        # only support recording state once
        if rid not in self.resources:
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


# by default just split by success/failure
def split_resources_by_results(resources, allowed_values=(), exclude=("error",)):
    return split_resources(
        resources,
        '"{}"[].status'.format(ActionResults.AnnotationKey),
        allowed_values=allowed_values,
        exclude=exclude,
    )


class Action(Element):

    permissions = ()
    metrics = ()

    log = logging.getLogger("custodian.actions")

    executor_factory = ThreadPoolExecutor
    permissions = ()
    schema = {'type': 'object'}
    schema_alias = None
    batch_size = 0
    concurrency = 2
    per_resource_results = True

    def __init__(self, data=None, manager=None, log_dir=None):
        self.data = data or {}
        self.manager = manager
        self.log_dir = log_dir
        self._client = None

        # let each action determine if they support the new results output
        if self.per_resource_results:
            self.id_key = manager.get_model().id if manager else 'id'
            self.results = ActionResults(self)

    def get_permissions(self):
        return self.permissions

    def get_client(self, service=None, **kwargs):
        return utils.local_session(self.manager.session_factory).client(
            service or self.manager.resource_type.service, **kwargs
        )

    def validate(self):
        return self

    @property
    def client(self):
        if not self._client:
            self._client = self.get_client()
        return self._client

    @property
    def name(self):
        return self.__class__.__name__.lower()

    def wrap_process(self, resources, event=None):
        if not self.data.get('include_failed', False):
            resources, failed = split_resources_by_results(resources)
        self.results.initialize(resources)
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

    def process(self, resources):
        raise NotImplementedError("Base action class does not implement behavior")

    # generic function for multi-worker execution
    def _process_with_futures(
        self,
        helper,
        resources,
        *args,
        max_workers=None,
        batch_size=None,
        exception_format=None,
        **kwargs
    ):

        # select setting based on arg, data, class default
        batch_size = batch_size or self.data.get('batch_size', self.batch_size)
        concurrency = max_workers or self.concurrency

        results = []
        if not resources:
            return results

        with self.executor_factory(concurrency) as w:
            futures = {}
            if batch_size > 0:
                # this is a list of resources passed to the helper
                for rs in utils.chunks(resources, size=batch_size):
                    futures[w.submit(helper, rs, *args, **kwargs)] = rs
            else:
                # a single resource passed to the helper
                for r in resources:
                    futures[w.submit(helper, r, *args, **kwargs)] = r

            for f in as_completed(futures):
                if f.exception():
                    r = futures[f]
                    fmt_vars = {
                        "action": self.name,
                        "count": len(r) if batch_size > 1 else 1,
                        "policy": self.manager.data.get('name'),
                        "error": f.exception(),
                    }
                    if batch_size == 0:
                        fmt = ("Error processing action:{action} resource:{resource}"
                               " policy:{policy} error:{error}")
                        fmt_vars["resource"] = r[self.id_key]
                    else:
                        fmt = ("Error batch processing action:{action} count:{count}"
                               " policy:{policy} error:{error}")
                    if exception_format:
                        fmt = exception_format
                    self.log.error(fmt.format(**fmt_vars))
                    self.results.error(r, f.exception())
                    self._exception_hook(r, f.exception())
                result = f.result()
                if result:
                    results.append(result)
        return results

    def _exception_hook(self, resource, e):
        return

    def _run_api(self, cmd, *args, **kw):
        try:
            return cmd(*args, **kw)
        except ClientError as e:
            if (
                e.response['Error']['Code'] == 'DryRunOperation'
                and e.response['ResponseMetadata']['HTTPStatusCode'] == 412
                and 'would have succeeded' in e.response['Error']['Message']
            ):
                return self.log.info(
                    "Dry run operation %s succeeded" % (self.__class__.__name__.lower())
                )
            raise


BaseAction = Action


class EventAction(BaseAction):
    """Actions which receive lambda event if present
    """
