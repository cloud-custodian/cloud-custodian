# Copyright 2019 Microsoft Corporation
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

import logging

from c7n_azure.constants import (CONTAINER_EVENT_TRIGGER_MODE,
                                 CONTAINER_TIME_TRIGGER_MODE)

from c7n import utils
from c7n.actions import EventAction
from c7n.policy import PullMode, ServerlessExecutionMode, execution


class AzureContainerHostMode(ServerlessExecutionMode):
    """A policy that runs/executes in container-host mode."""

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'execution-options': {'type': 'object'}
        }
    }

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    def __init__(self, policy):
        self.policy = policy
        self.log = logging.getLogger('custodian.azure.AzureContainerHostMode')

    def run(self, event=None, lambda_context=None):
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        pass


@execution.register(CONTAINER_TIME_TRIGGER_MODE)
class AzureContainerPeriodicMode(AzureContainerHostMode, PullMode):
    """A policy that runs at specified time intervals."""
    schema = utils.type_schema(CONTAINER_TIME_TRIGGER_MODE,
                               schedule={'type': 'string'},
                               rinherit=AzureContainerHostMode.schema)

    def provision(self):
        super(AzureContainerPeriodicMode, self).provision()

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        return PullMode.run(self)

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")


@execution.register(CONTAINER_EVENT_TRIGGER_MODE)
class AzureContainerEventMode(AzureContainerHostMode):
    """A policy that runs at specified time intervals."""
    schema = utils.type_schema(CONTAINER_EVENT_TRIGGER_MODE,
                               events={'type': 'array', 'items': {
                                   'oneOf': [
                                       {'type': 'string'},
                                       {'type': 'object',
                                        'required': ['resourceProvider', 'event'],
                                        'properties': {
                                            'resourceProvider': {'type': 'string'},
                                            'event': {'type': 'string'}}}]
                               }},
                               rinherit=AzureContainerHostMode.schema)

    def provision(self):
        super(AzureContainerEventMode, self).provision()

    def run(self, event=None, lambda_context=None):
        resources = self.policy.resource_manager.get_resources([event['subject']])

        resources = self.policy.resource_manager.filter_resources(
            resources, event)

        if not resources:
            self.policy.log.info(
                "policy: %s resources: %s no resources found" % (
                    self.policy.name, self.policy.resource_type))
            return

        resources = self.policy.resource_manager.filter_resources(
            resources, event)

        with self.policy.ctx:
            self.policy.ctx.metrics.put_metric(
                'ResourceCount', len(resources), 'Count', Scope="Policy",
                buffer=False)

            self.policy._write_file(
                'resources.json', utils.dumps(resources, indent=2))

            for action in self.policy.resource_manager.actions:
                self.policy.log.info(
                    "policy: %s invoking action: %s resources: %d",
                    self.policy.name, action.name, len(resources))
                if isinstance(action, EventAction):
                    results = action.process(resources, event)
                else:
                    results = action.process(resources)
                self.policy._write_file(
                    "action-%s" % action.name, utils.dumps(results))

        return resources

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")
