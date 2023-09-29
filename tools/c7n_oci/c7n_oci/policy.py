# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import time

from c7n_oci import mu

from c7n import utils
from c7n.exceptions import PolicyValidationError
from c7n.policy import ServerlessExecutionMode, execution
from c7n.utils import type_schema


class FunctionMode(ServerlessExecutionMode):
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'execution-options': {'type': 'object'},
            'subnets': {'type': 'array'},
            'function-prefix': {'type': 'string'},
            'timeout': {'type': 'number'},
            'memory': {'type': 'number'},
            'freeform_tags': {'type': 'object'},
        },
        'required': ['subnets'],
    }

    def __init__(self, policy):
        self.policy = policy
        self.log = logging.getLogger('custodian.oci.functionexec')

    def run(self):
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        with self.policy.ctx:
            self.policy.log.info("Provisioning policy function %s", self.policy.name)
            manager = mu.FunctionManager(self.policy.session_factory)
            return manager.publish(self.get_function())

    def deprovision(self):
        self.log.info("Removing policy function %s", self.policy.name)
        manager = mu.FunctionManager(self.policy.session_factory)
        return manager.remove(self.get_function())

    def validate(self):
        prefix = self.policy.data['mode'].get('function-prefix', 'custodian-')
        MAX_FUNCTION_NAME_LENGTH = 255
        if len(prefix + self.policy.name) > MAX_FUNCTION_NAME_LENGTH:
            raise PolicyValidationError(
                (
                    f"OCI Custodian Function policies have a max length "
                    f"with prefix of {MAX_FUNCTION_NAME_LENGTH}"
                    f" policy:{prefix} prefix:{self.policy.name}"
                )
            )

    def get_function(self):
        raise NotImplementedError("subclass responsibility")


@execution.register('oci-event')
class EventMode(FunctionMode):
    """
    This mode provides policy level execution against \
    Oracle Cloud Infrastructure Events \
        https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm.
    Each Custodian policy is deployed as an independent OCI Cloud function.
    Review the Oracle Cloud Infrastructure services that emit events. \
    https://docs.oracle.com/en-us/iaas/Content/Events/Reference/eventsproducers.htm
    """

    schema = type_schema(
        'oci-event',
        delay={
            'type': 'integer',
            'description': 'sleep for delay seconds before processing an event',
        },
        events={
            'type': 'array',
            'items': {'type': 'string'},
        },
        required=['events', 'subnets'],
        rinherit=FunctionMode.schema,
    )

    def resolve_resources(self, event):
        """Resolve a resource from its event metadata."""
        delay = self.policy.data.get('mode', {}).get('delay')
        if delay:
            time.sleep(delay)
        resources = []
        if event:
            resource_params_values = []
            get_params = self.policy.resource_manager.resource_type.get_params
            if get_params:
                extra_params = self.policy.resource_manager.get_extra_params()
                for param in get_params:
                    # namespace name in the event object is not consistent,
                    # so using same approach as query.py -
                    # _get_resources_with_compartment_and_params
                    resource_params_values.append(
                        extra_params[param] if extra_params.get(param) else event['data'][param]
                    )

            else:
                resource_params_values = [event['data']['resourceId']]
            resources.append(resource_params_values)
        return resources

    def get_function(self):
        return mu.PolicyFunction(self.policy)

    def validate(self):
        super().validate()
        if not os.environ.get('OCI_AUTH_TOKEN') and not all(
            os.environ.get(env)
            for env in [
                'OCI_RESOURCE_PRINCIPAL_RPST',
                'OCI_RESOURCE_PRINCIPAL_PRIVATE_PEM',
                'OCI_RESOURCE_PRINCIPAL_REGION',
            ]
        ):
            # https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrygettingauthtoken.htm
            raise PolicyValidationError(
                "OCI_AUTH_TOKEN enviornment variable is not set or it is empty. \
It is required to log in to Oracle Cloud Infrastructure Registry."
            )
        if not self.policy.resource_manager.resource_type.event_service_name:
            raise PolicyValidationError(
                "Resource:%s is not supported by event mode currently" % (self.policy.resource_type)
            )
        if not self.policy.resource_manager.resource_type.get:
            raise PolicyValidationError(
                "Resource:%s does not implement retrieval method" % (self.policy.resource_type)
            )

    def run(self, event, context):
        from c7n.actions import EventAction

        resources = self.resolve_resources(event)
        self.policy.log.info("Total resources resolved from event  %d" % len(resources))
        if not resources:
            return
        resources = self.policy.resource_manager.get_resources_details(resources)

        resources = self.policy.resource_manager.filter_resources(resources)

        self.policy.log.info("Filtered resources %d" % len(resources))

        if not resources:
            return

        with self.policy.ctx as ctx:
            ctx.metrics.put_metric(
                'ResourceCount', len(resources), 'Count', Scope="Policy", buffer=False
            )
            ctx.output.write_file('resources.json', utils.dumps(resources, indent=2))
            for action in self.policy.resource_manager.actions:
                if isinstance(action, EventAction):
                    results = action.process(resources, event)
                else:
                    results = action.process(resources)
                ctx.output.write_file("action-%s" % action.name, utils.dumps(results))
        return resources
