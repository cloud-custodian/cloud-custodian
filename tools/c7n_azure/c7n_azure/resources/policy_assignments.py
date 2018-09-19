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

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager

from azure.mgmt.policyinsights import PolicyInsightsClient
from c7n_azure.utils import StringUtils


@resources.register('policyassignments')
class PolicyAssignments(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.resource.policy'
        client = 'PolicyClient'
        enum_spec = ('policy_assignments', 'list', None)
        type = 'policyassignments'

    def augment(self, resources):
        s = self.get_session()
        client = PolicyInsightsClient(s.get_credentials())

        query = client.policy_states.list_query_results_for_subscription(
            policy_states_resource='latest', subscription_id=s.subscription_id).value

        for r in resources:
            filtered = [f for f in query if StringUtils.equal(f.policy_assignment_id, r['id'])]
            non_complaint_resources = [{
                'resourceId': f.resource_id,
                'resourceType': f.resource_type,
                'resourceGroup': f.resource_group} for f in filtered]
            r['nonComplaintResources'] = non_complaint_resources

        return resources
