# Copyright 2018 Capital One Services, LLC
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

from c7n.exceptions import PolicyValidationError
from c7n.policy import execution, ServerlessExecutionMode
from c7n.utils import local_session, type_schema

from c7n_gcp import mu


class FunctionMode(ServerlessExecutionMode):

    schema = type_schema(
        'gcp-audit',
        **{'execution-options': {'type': 'object'},
           'timeout': {'type': 'string'},
           'memory-size': {'type': 'integer'},
           'labels': {'type': 'object'},
           'network': {'type': 'string'},
           'max-instances': {'type': 'integer'},
           'environment': {'type': 'object'}})

    def __init__(self, policy):
        self.policy = policy
        self.log = logging.getLogger('custodian.gcp.funcexec')

    def run(self):
        raise NotImplementedError("subclass responsibility")

    def validate(self):
        pass


@execution.register('gcp-audit')
class ApiAuditMode(FunctionMode):
    """Custodian policy execution on gcp api audit logs
    """

    schema = type_schema(
        'gcp-audit',
        methods={'type': 'array', 'items': {'type': 'string'}},
        required=['methods'],
        rinherit=FunctionMode.schema)

    def resolve_resources(self, event):
        """Resolve a gcp resource from its audit trail metadata.
        """
        if self.policy.resource_manager.resource_type.get_requires_event:
            return [self.policy.resource_manager.get_resource(event)]
        resource_info = event.get('resource')
        if resource_info is None or 'labels' not in resource_info:
            self.policy.log.warning("Could not find resource information in event")
            return
        # copy resource name, the api doesn't like resource ids, just names.
        if 'resourceName' in event['protoPayload']:
            resource_info['labels']['resourceName'] = event['protoPayload']['resourceName']

        resource = self.policy.resource_manager.get_resource(resource_info['labels'])
        return [resource]

    def _get_function(self):
        events = [mu.ApiSubscriber(
            local_session(self.policy.session_factory),
            {'methods': self.policy.data['mode']['methods']})]
        return mu.PolicyFunction(self.policy, events=events)

    def provision(self):
        self.log.info("Provisioning policy function %s", self.policy.name)
        manager = mu.CloudFunctionManager(self.policy.session_factory)
        return manager.publish(self._get_function())

    def deprovision(self):
        manager = mu.CloudFunctionManager(self.policy.session_factory)
        return manager.remove(self._get_function())

    def validate(self):
        if not self.policy.resource_manager.resource_type.get:
            raise PolicyValidationError(
                "Resource:%s does not implement retrieval method" % (
                    self.policy.resource_type))

    def run(self, event, context):
        """Execute a gcp serverless model"""
        resources = self.resolve_resources(event)
        if not resources:
            return

        resources = self.policy.resource_manager.filter_resources(
            resources, event)

        self.policy.log.info("Filtered resources %d" % len(resources))

        if not resources:
            return

        for action in self.policy.resource_manager.actions:
            action.process(resources)

        return resources
