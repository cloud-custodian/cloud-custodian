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

    def test_ses_configuration_set_delete(self):
        session_factory = self.replay_flight_data("test_ses_configuration_set_delete")
        p = self.load_policy(
            {
                "name": "ses-configuration_set-delete-test",
                "resource": "ses-configuration-set",
                "actions": [{"type": "delete"}],
            }, session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        p = self.load_policy(
            {
                "name": "ses-configuration-set-delete-test",
                "resource": "ses-configuration-set",
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_ses_receipt_rule_set_query(self):
        session_factory = self.replay_flight_data("test_ses_rule_set_query")
        p = self.load_policy(
            {
                "name": "ses-receipt-rule-set-query-test",
                "resource": "ses-receipt-rule-set",
                "filters": [{"type": "value",
                             "key": "Rules[0].Enabled",
                             "op": "eq",
                             "value": True}
                            ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_ses_receipt_rule_set_delete(self):
        session_factory = self.replay_flight_data("test_ses_rule_set_delete")
        p = self.load_policy(
            {
                "name": "ses-receipt-rule_set-delete-test",
                "resource": "ses-receipt-rule-set",
                "filters": [{"type": "value",
                             "key": "Rules[:].Enabled",
                             "op": "in",
                             "value": True,
                             "value_type": "swap"}
                            ],
                "actions": [{"type": "delete"}],
            }, session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        p = self.load_policy(
            {
                "name": "ses-receipt-rule-delete-test",
                "resource": "ses-receipt-rule-set",
                "filters": [{"type": "value",
                             "key": "Rules[:].Enabled",
                             "op": "in",
                             "value": True,
                             "value_type": "swap"}
                            ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)


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

    def test_ses_email_identity_has_statement_definition(self):
        session_factory = self.replay_flight_data("test_ses_email_identity_has_statement")
        p = self.load_policy(
            {
                "name": "test_ses_email_identity_has_statement_definition",
                "resource": "ses-email-identity",
                "filters": [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Deny",
                                "Action": "ses:SendEmail",
                                "Principal": {"AWS": "*"},
                                "Condition":
                                    {"StringNotEquals": {"ses:FromAddress": "*test*"}},
                                "Resource": "arn:aws:ses:us-west-2:644160558196:identity/c7n@t.com"
                            }
                        ]
                    }
                ],
            }, session_factory=session_factory,
            config={'region': 'us-west-2'},
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]["IdentityName"], "c7n@t.com")

    def test_ses_email_identity_has_statement_star_definition(self):
        session_factory = self.replay_flight_data("test_ses_email_identity_has_statement")
        p = self.load_policy(
            {
                "name": "test_ses_email_identity_has_statement_star_definition",
                "resource": "ses-email-identity",
                "filters": [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Deny",
                                "Action": "ses:SendEmail",
                                "Principal": "*",
                                "Condition":
                                    {"StringNotLike": {"ses:FromAddress": "*test*"}},
                                "Resource": "arn:aws:ses:us-west-2:644160558196:identity/c7n@t.com"
                            }
                        ]
                    }
                ],
            }, session_factory=session_factory,
            config={'region': 'us-west-2'},
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]["IdentityName"], "c7n@t.com")

    def test_ses_email_identity_has_statement_id(self):
        session_factory = self.replay_flight_data("test_ses_email_identity_has_statement")
        p = self.load_policy(
            {
                "name": "test_ses_email_identity_has_statement_id",
                "resource": "ses-email-identity",
                "filters": [
                    {
                        "type": "has-statement",
                        "statement_ids": ["AllowStatement"]
                    }
                ],
            }, session_factory=session_factory,
            config={'region': 'us-west-2'},
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(resources[0]["IdentityName"], "c7n@t.com")

    def test_ses_dedicated_ip_pool_query(self):
        session_factory = self.replay_flight_data("test_ses_dedicated_ip_pool_query")
        p = self.load_policy(
            {
                "name": "ses-dedicated-ip-pool-query",
                "resource": "ses-dedicated-ip-pool",
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        for r in resources:
            self.assertTrue("ScalingMode" in r)
            self.assertTrue("Tags" in r)
