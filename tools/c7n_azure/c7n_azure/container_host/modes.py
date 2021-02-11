# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

from c7n_azure.constants import (CONTAINER_EVENT_TRIGGER_MODE,
                                 CONTAINER_TIME_TRIGGER_MODE)
from c7n_azure.policy import AzureModeCommon

from c7n import utils
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

    log = logging.getLogger('custodian.azure.AzureContainerHostMode')

    def __init__(self, policy):
        self.policy = policy

    def run(self, event=None, lambda_context=None):
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        pass


@execution.register(CONTAINER_TIME_TRIGGER_MODE)
class AzureContainerPeriodicMode(AzureContainerHostMode, PullMode):
    """A policy that runs at specified time intervals."""
    # Pattern based on apscheduler's CronTrigger:
    # https://github.com/agronholm/apscheduler/tree/master/apscheduler/triggers/cron
    schedule_regex = (r'^\s?(\*|[0-9]|\,|\/|\-)+ '
                      r'(\*|[0-9]|\,|\/|\-)+ '
                      r'(\*|[1-9]|[1-2][0-9]|3[0-1]|\,|\*\/|\-)+ '
                      r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|'
                      r'\,|\*\/|[1-9]|1[0-2]|\*)+ '
                      r'(mon|tue|wed|thu|fri|sat|sun|[0-6]|\,|\*|\-)+\s?$')
    schema = utils.type_schema(CONTAINER_TIME_TRIGGER_MODE,
                               schedule={'type': 'string', 'pattern': schedule_regex},
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
        return AzureModeCommon.run_for_event(self.policy, event)

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")
