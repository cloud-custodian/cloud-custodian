# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.policy import execution, ServerlessExecutionMode
from .mu import HookPolicy, HookManager


@execution.register("cfn-hook")
class HookMode(ServerlessExecutionMode):

    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["exec-role", "log-role"],
        "properties": {
            "type": {"enum": ["cfn-hook"]},
            "match-compliant": {"type": "boolean"},
            "action": {"enum": ["FAIL", "WARN"]},
            "exec-role": {"type": "string"},
            "log-role": {"type": "string"},
        },
    }

    def provision(self):
        hook_policy = HookPolicy(self.policy)
        manager = HookManager(self)
        manager.add(hook_policy)

    def run(self, event, lambda_context):
        if not self.policy.is_runnable(event):
            return

        resources = self.resolve_resources(event)
        rcount = len(resources)

        self.policy.resource_manager.filter_resources(resources, event)
        self.policy.log.info("Filtered resources %d of %d", len(resources), rcount)

    def resolve_resources(self, event):
        pass
