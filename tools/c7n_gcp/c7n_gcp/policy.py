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

from c7n.policy import execution
from c7n.utils import type_schema

from c7n_gcp.mu import CloudFunctionManager, PolicyFunction


class FunctionMode(object):

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

    def provision(self):
        self.log.info("Provisioning policy function %s", self.policy.name)
        manager = CloudFunctionManager(self.policy.session_factory)
        return manager.publish(PolicyFunction(self.policy))

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
        rinherit=FunctionMode.schema)
    
    def resolve_resources(self, event):
        """Resolve a gcp resource from its audit trail metadata.
        """
        resource_info = event.get('resource')
        if resource_info is None or 'labels' not in resource_info:
            self.policy.log.warning("Could not find resource information in event")
            return
        resource = self.policy.resource_manager.get_resource(resource_info['labels'])
        return [resource]

    def run(self, event, context):
        """Execute a gcp serverless model"""
        resources = self.resolve_resources(event)
        if not resources:
            return

        resources = self.policy.resource_manager.filter_resources(
            resources, event)

        if 'debug' in event:
            self.policy.log.info("Filtered resources %d" % len(resources))

        if not resources:
            return
        
        for action in self.policy.resource_manager.actions:
            results = action.process(resources)

        return resources

        

