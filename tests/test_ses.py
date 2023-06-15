# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class SESTest(BaseTest):

    def test_ses_configuration_set_query(self):
        session_factory = self.replay_flight_data("test_ses_configuration_set_query")
        p = self.load_policy(
            {
                "name": "ses-configuration-set-query-test",
                "resource": "ses-configuration-set"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_ses_configuration_set_delivery_options(self):
        session_factory = self.replay_flight_data("test_ses_configuration_set_delivery_options")
        p = self.load_policy(
            {
                "name": "ses-configuration-set-delivery-options-test",
                "resource": "ses-configuration-set",
                "filters": [{"type": "value",
                             "key": "DeliveryOptions.TlsPolicy",
                             "op": "eq",
                             "value": "Optional"},
                            ],
                "actions": [
                    {
                        "type": "set-delivery-options",
                        "tls-policy": "Require"
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        client = session_factory().client('ses')
        for r in resources:
            response = client.describe_configuration_set(ConfigurationSetName=r["Name"],
                                                         ConfigurationSetAttributeNames=['deliveryOptions'])
            tls_policy = response['DeliveryOptions']['TlsPolicy']
            self.assertEqual(tls_policy, "Require")


class SESV2Test(BaseTest):

    def test_ses_email_identity_query(self):
        session_factory = self.replay_flight_data("test_ses_email_identity_query")
        p = self.load_policy(
            {
                "name": "ses-email-identity-query-test",
                "resource": "ses-email-identity"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
