# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from gcp_common import BaseTest, event_data


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

        self.assertEqual(
            policy.resource_manager.get_urns(billingaccount_resources),
            ["gcp:cloudbilling::cloud-custodian:account/CU570D-1A4CU5-70D1A4"],
        )

    def test_billingaccount_get(self):
        billingaccount_resource_name = 'billingAccounts/CU570D-1A4CU5-70D1A4'
        session_factory = self.replay_flight_data(
            'cloudbilling-account-get')

        policy = self.load_policy(
            {'name': 'billing-cloudbilling-account-audit',
             'resource': 'gcp.cloudbilling-account',
             'mode': {
                 'type': 'gcp-audit',
                 'methods': ['AssignProjectToBillingAccount']
             }},
            session_factory=session_factory)

        exec_mode = policy.get_execution_mode()
        event = event_data('cloudbilling-account-assign.json')

        resources = exec_mode.run(event, None)
        self.assertEqual(resources[0]['name'], billingaccount_resource_name)

        self.assertEqual(
            policy.resource_manager.get_urns(resources),
            ["gcp:cloudbilling::cloud-custodian:account/CU570D-1A4CU5-70D1A4"],
        )
