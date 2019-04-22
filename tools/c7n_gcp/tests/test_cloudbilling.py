# Copyright 2019 Capital One Services, LLC
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

from gcp_common import BaseTest


class CloudBillingAccountTest(BaseTest):

    def test_billingaccount_query(self):
        billingaccount_resource_name = 'billingAccounts/CU570D-1A4CU5-70D1A4'
        session_factory = self.replay_flight_data(
            'cloudbilling-account-query')

        policy = self.load_policy(
            {'name': 'billing-cloudbilling-account-dryrun',
             'resource': 'gcp.cloudbilling-account'},
            session_factory=session_factory)

        billingaccount_resources = policy.run()
        self.assertEqual(billingaccount_resources[0]['name'], billingaccount_resource_name)

    def test_billingaccount_get(self):
        billingaccount_resource_name = 'billingAccounts/CU570D-1A4CU5-70D1A4'
        session_factory = self.replay_flight_data(
            'cloudbilling-account-get')

        policy = self.load_policy(
            {'name': 'billing-cloudbilling-account-dryrun',
             'resource': 'gcp.cloudbilling-account'},
            session_factory=session_factory)

        billingaccount_resource = policy.resource_manager.get_resource(
            {'name': billingaccount_resource_name})
        self.assertEqual(billingaccount_resource['name'], billingaccount_resource_name)
