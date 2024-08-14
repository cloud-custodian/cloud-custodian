# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class ConnectTest(BaseTest):

    def test_connect_query(self):
        session_factory = self.replay_flight_data("test_connect_query")
        p = self.load_policy(
            {
                "name": "connect-query-test",
                "resource": "connect-instance"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connect_instance_attribute(self):
        session_factory = self.replay_flight_data("test_connect_instance_attribute")
        p = self.load_policy(
            {
                "name": "connect-instance-attribute-test",
                "resource": "connect-instance",
                "filters": [{
                    'type': 'instance-attribute',
                    'key': 'Attribute.Value',
                    'value': 'true',
                    'attribute_type': 'CONTACT_LENS'
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connect_set_attributes_true(self):
        session_factory = self.replay_flight_data("test_connect_set_attributes_true")
        p = self.load_policy(
            {
                "name": "connect-instance-set-contact-lens",
                "resource": "connect-instance",
                "filters": [{
                    'type': 'instance-attribute',
                    'key': 'Attribute.Value',
                    'value': 'false',
                    'attribute_type': 'CONTACT_LENS'
                }],
                "actions": [
                    {'type': 'set-attributes',
                    "attribute_type": "CONTACT_LENS",
                    "value": "true"}
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        results = []
        for r in resources:
            results.append(
                session_factory().client('connect').describe_instance_attribute(
                    InstanceId=r["Id"],
                    AttributeType=r["c7n:InstanceAttribute"]["Attribute"]["AttributeType"])
            )

        self.assertEqual(results[0]["Attribute"]["AttributeType"], "CONTACT_LENS")
        self.assertEqual(results[0]["Attribute"]["Value"], "true")
        self.assertEqual(len(resources), 1)

    def test_connect_set_attributes_false(self):
        session_factory = self.replay_flight_data("test_connect_set_attributes_false")
        p = self.load_policy(
            {
                "name": "connect-instance-disable-contact-lens-test",
                "resource": "connect-instance",
                "filters": [{
                    'type': 'instance-attribute',
                    'key': 'Attribute.Value',
                    'value': 'true',
                    'attribute_type': 'CONTACT_LENS'
                }],
                "actions": [
                    {'type': 'set-attributes',
                    "attribute_type": "CONTACT_LENS",
                    "value": "false"}
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        results = []
        for r in resources:
            results.append(
                session_factory().client('connect').describe_instance_attribute(
                    InstanceId=r["Id"],
                    AttributeType=r["c7n:InstanceAttribute"]["Attribute"]["AttributeType"])
            )
        self.assertEqual(results[0]["Attribute"]["AttributeType"], "CONTACT_LENS")
        self.assertEqual(results[0]["Attribute"]["Value"], "false")
        self.assertEqual(len(resources), 1)


class ConnectCampaignTest(BaseTest):
    def test_connect_campaign_query(self):
        session_factory = self.replay_flight_data("test_connect_campaign_query")
        p = self.load_policy(
            {
                "name": "connect-campaign-query-test",
                "resource": "connect-campaign"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(2, len(resources))

    def test_connect_campaign_instance_config(self):
        session_factory = self.replay_flight_data("test_connect_campaign_instance_config_filter")
        p = self.load_policy(
            {
                "name": "connect-instance-attribute-test",
                "resource": "connect-campaign",
                'filters': [
                    {
                        'type': 'value',
                        'key': 'connectInstanceConfig.encryptionConfig.enabled',
                        'value': True
                    }
                ]
            }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_connect_campaign_kms_filter(self):
        session_factory = self.replay_flight_data("test_connect_campaign_kms_filter")
        p = self.load_policy(
            {
                "name": "connect-instance-attribute-test",
                "resource": "connect-campaign",
                'filters': [
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/eks'
                    }
                ]
            }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
