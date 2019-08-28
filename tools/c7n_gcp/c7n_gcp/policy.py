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

from dateutil.tz import tz

from c7n.exceptions import PolicyValidationError
from c7n.policy import execution, ServerlessExecutionMode, PullMode
from c7n.utils import local_session, type_schema

from c7n_gcp import mu

DEFAULT_REGION = 'us-central1'


class FunctionMode(ServerlessExecutionMode):

    schema = type_schema(
        'gcp',
        **{'execution-options': {'type': 'object'},
           'timeout': {'type': 'string'},
           'memory-size': {'type': 'integer'},
           'labels': {'type': 'object'},
           'network': {'type': 'string'},
           'max-instances': {'type': 'integer'},
           'service-account': {'type': 'string'},
           'environment': {'type': 'object'}})

    def __init__(self, policy):
        self.policy = policy
        self.log = logging.getLogger('custodian.gcp.funcexec')
        self.region = policy.options.regions[0] if len(policy.options.regions) else DEFAULT_REGION

    def run(self):
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        self.log.info("Provisioning policy function %s", self.policy.name)
        manager = mu.CloudFunctionManager(self.policy.session_factory, self.region)
        return manager.publish(self._get_function())

    def deprovision(self):
        manager = mu.CloudFunctionManager(self.policy.session_factory, self.region)
        return manager.remove(self._get_function())

    def validate(self):
        pass

    def _get_function(self):
        raise NotImplementedError("subclass responsibility")


@execution.register('gcp-periodic')
class PeriodicMode(FunctionMode, PullMode):

    schema = type_schema(
        'gcp-periodic',
        rinherit=FunctionMode.schema,
        required=['schedule'],
        **{'trigger-type': {'enum': ['http', 'pubsub']},
           'tz': {'type': 'string'},
           'schedule': {'type': 'string'}})

    def validate(self):
        mode = self.policy.data['mode']
        if 'tz' in mode:
            error = PolicyValidationError(
                "policy:%s gcp-periodic invalid tz:%s" % (
                    self.policy.name, mode['tz']))
            # We can't catch all errors statically, our local tz retrieval
            # then the form gcp is using, ie. not all the same aliases are
            # defined.
            tzinfo = tz.gettz(mode['tz'])
            if tzinfo is None:
                raise error

    def _get_function(self):
        events = [mu.PeriodicEvent(
            local_session(self.policy.session_factory),
            self.policy.data['mode'],
            self.region
        )]
        return mu.PolicyFunction(self.policy, events=events)

    def run(self, event, context):
        return PullMode.run(self)


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
            self.policy.data['mode'])]
        return mu.PolicyFunction(self.policy, events=events)

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
