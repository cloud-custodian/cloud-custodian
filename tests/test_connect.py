# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class ConnectInstanceTest(BaseTest):

    def test_connect_instance_query(self):
        session_factory = self.replay_flight_data("test_connect_instance_query")
        p = self.load_policy(
            {
                "name": "connect-instance-query-test",
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


class ConnectUserTest(BaseTest):

    def test_connect_user_query(self):
        session_factory = self.replay_flight_data("test_connect_user_query")
        p = self.load_policy(
            {
                "name": "connect-user-query-test",
                "resource": "connect-user"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connect_user_tagging(self):
        session_factory = self.replay_flight_data("test_connect_user_tagging")
        client = session_factory().client("connect")

        p = self.load_policy(
            {
                "name": "connect-user-mark-for-op-test",
                "resource": "connect-user",
                "filters": [{'tag:c7n': 'True'}],
                'actions': [{
                    'type': 'mark-for-op',
                    'tag': 'custodian_cleanup',
                    'op': 'notify',
                    'days': 4
                }]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "connect-user-tag-test",
                "resource": "connect-user",
                "filters": [
                    {'tag:custodian_cleanup': 'Resource does not meet policy: notify@2022/09/19'}
                ],
                "actions": [
                    {"type": "tag", "key": "abcd", "value": "xyz"},
                    {"type": "remove-tag", "tags": ["custodian_cleanup"]},
                ],
            }, session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['Arn']
        tags = client.list_tags_for_resource(resourceArn=arn)
        self.assertEqual(tags.get('tags'), {'c7n': 'True', 'abcd': 'xyz'})


class ConnectRoutingProfileTest(BaseTest):

    def test_connect_routing_profile_query(self):
        session_factory = self.replay_flight_data("test_connect_routing_profile_query")
        p = self.load_policy(
            {
                "name": "connect-routing-profile-query-test",
                "resource": "connect-routing-profile"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connect_routing_profile_tagging(self):
        session_factory = self.replay_flight_data("test_connect_routing_profile_tagging")
        client = session_factory().client("connect")

        p = self.load_policy(
            {
                "name": "connect-routing-profile-mark-for-op-test",
                "resource": "connect-routing-profile",
                "filters": [{'tag:c7n': 'True'}],
                'actions': [{
                    'type': 'mark-for-op',
                    'tag': 'custodian_cleanup',
                    'op': 'notify',
                    'days': 4
                }]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "connect-routing-profile-tag-test",
                "resource": "connect-routing-profile",
                "filters": [
                    {'tag:custodian_cleanup': 'Resource does not meet policy: notify@2022/09/19'}
                ],
                "actions": [
                    {"type": "tag", "key": "abcd", "value": "xyz"},
                    {"type": "remove-tag", "tags": ["custodian_cleanup"]},
                ],
            }, session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['RoutingProfileArn']
        tags = client.list_tags_for_resource(resourceArn=arn)
        self.assertEqual(tags.get('tags'), {'c7n': 'True', 'abcd': 'xyz'})


class ConnectQueueTest(BaseTest):

    def test_connect_queue_query(self):
        session_factory = self.replay_flight_data("test_connect_queue_query")
        p = self.load_policy(
            {
                "name": "connect-queue-query-test",
                "resource": "connect-queue"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connect_queue_tagging(self):
        session_factory = self.replay_flight_data("test_connect_queue_tagging")
        client = session_factory().client("connect")

        p = self.load_policy(
            {
                "name": "connect-queue-mark-for-op-test",
                "resource": "connect-queue",
                "filters": [{'tag:c7n': 'True'}],
                'actions': [{
                    'type': 'mark-for-op',
                    'tag': 'custodian_cleanup',
                    'op': 'notify',
                    'days': 4
                }]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "connect-queue-tag-test",
                "resource": "connect-queue",
                "filters": [
                    {'tag:custodian_cleanup': 'Resource does not meet policy: notify@2022/09/19'}
                ],
                "actions": [
                    {"type": "tag", "key": "abcd", "value": "xyz"},
                    {"type": "remove-tag", "tags": ["custodian_cleanup"]},
                ],
            }, session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['QueueArn']
        tags = client.list_tags_for_resource(resourceArn=arn)
        self.assertEqual(tags.get('tags'), {'c7n': 'True', 'abcd': 'xyz'})


class ConnectQuickConnectTest(BaseTest):

    def test_connect_quick_connect_query(self):
        session_factory = self.replay_flight_data("test_connect_quick_connect_query")
        p = self.load_policy(
            {
                "name": "connect-quick_connect-query-test",
                "resource": "connect-quick-connect"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connect_quick_connect_tagging(self):
        session_factory = self.replay_flight_data("test_connect_quick_connect_tagging")
        client = session_factory().client("connect")

        p = self.load_policy(
            {
                "name": "connect-quick-connect-mark-for-op-test",
                "resource": "connect-quick-connect",
                "filters": [{'tag:c7n': 'True'}],
                'actions': [{
                    'type': 'mark-for-op',
                    'tag': 'custodian_cleanup',
                    'op': 'notify',
                    'days': 4
                }]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "connect-quick-connect-tag-test",
                "resource": "connect-quick-connect",
                "filters": [
                    {'tag:custodian_cleanup': 'Resource does not meet policy: notify@2022/09/19'}
                ],
                "actions": [
                    {"type": "tag", "key": "abcd", "value": "xyz"},
                    {"type": "remove-tag", "tags": ["custodian_cleanup"]},
                ],
            }, session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['QuickConnectARN']
        tags = client.list_tags_for_resource(resourceArn=arn)
        self.assertEqual(tags.get('tags'), {'c7n': 'True', 'abcd': 'xyz'})


class ConnectContactFlowTest(BaseTest):

    def test_connect_contact_flow_query(self):
        session_factory = self.replay_flight_data("test_connect_contact_flow_query")
        p = self.load_policy(
            {
                "name": "connect-contact-flow-query-test",
                "resource": "connect-contact-flow"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connect_contact_flow_tagging(self):
        session_factory = self.replay_flight_data("test_connect_contact_flow_tagging")
        client = session_factory().client("connect")

        p = self.load_policy(
            {
                "name": "connect-contact-flow-mark-for-op-test",
                "resource": "connect-contact-flow",
                "filters": [{'tag:c7n': 'True'}],
                'actions': [{
                    'type': 'mark-for-op',
                    'tag': 'custodian_cleanup',
                    'op': 'notify',
                    'days': 4
                }]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "connect-contact-flow-tag-test",
                "resource": "connect-contact-flow",
                "filters": [
                    {'tag:custodian_cleanup': 'Resource does not meet policy: notify@2022/09/19'}
                ],
                "actions": [
                    {"type": "tag", "key": "abcd", "value": "xyz"},
                    {"type": "remove-tag", "tags": ["custodian_cleanup"]},
                ],
            }, session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['Arn']
        tags = client.list_tags_for_resource(resourceArn=arn)
        self.assertEqual(tags.get('tags'), {'c7n': 'True', 'abcd': 'xyz'})


class ConnectAgentStatusTest(BaseTest):

    def test_connect_agent_status_query(self):
        session_factory = self.replay_flight_data("test_connect_agent_status_query")
        p = self.load_policy(
            {
                "name": "connect-agent-status-query-test",
                "resource": "connect-agent-status"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connect_agent_status_tagging(self):
        session_factory = self.replay_flight_data("test_connect_agent_status_tagging")
        client = session_factory().client("connect")

        p = self.load_policy(
            {
                "name": "connect-agent-status-mark-for-op-test",
                "resource": "connect-agent-status",
                "filters": [{'tag:c7n': 'True'}],
                'actions': [{
                    'type': 'mark-for-op',
                    'tag': 'custodian_cleanup',
                    'op': 'notify',
                    'days': 4
                }]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "connect-agent-status-tag-test",
                "resource": "connect-agent-status",
                "filters": [
                    {'tag:custodian_cleanup': 'Resource does not meet policy: notify@2022/09/19'}
                ],
                "actions": [
                    {"type": "tag", "key": "abcd", "value": "xyz"},
                    {"type": "remove-tag", "tags": ["custodian_cleanup"]},
                ],
            }, session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['AgentStatusARN']
        tags = client.list_tags_for_resource(resourceArn=arn)
        self.assertEqual(tags.get('tags'), {'c7n': 'True', 'abcd': 'xyz'})


class ConnectHoursOfOperationTest(BaseTest):

    def test_connect_hours_of_operation_query(self):
        session_factory = self.replay_flight_data("test_connect_hours_of_operation_query")
        p = self.load_policy(
            {
                "name": "connect-hours-of-operation-query-test",
                "resource": "connect-hours-of-operation"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connect_hours_of_operation_tagging(self):
        session_factory = self.replay_flight_data("test_connect_hours_of_operation_tagging")
        client = session_factory().client("connect")

        p = self.load_policy(
            {
                "name": "connect-hours-of-operation-mark-for-op-test",
                "resource": "connect-hours-of-operation",
                "filters": [{'tag:c7n': 'True'}],
                'actions': [{
                    'type': 'mark-for-op',
                    'tag': 'custodian_cleanup',
                    'op': 'notify',
                    'days': 4
                }]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "connect-hours-of-operation-tag-test",
                "resource": "connect-hours-of-operation",
                "filters": [
                    {'tag:custodian_cleanup': 'Resource does not meet policy: notify@2022/09/19'}
                ],
                "actions": [
                    {"type": "tag", "key": "abcd", "value": "xyz"},
                    {"type": "remove-tag", "tags": ["custodian_cleanup"]},
                ],
            }, session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['HoursOfOperationArn']
        tags = client.list_tags_for_resource(resourceArn=arn)
        self.assertEqual(tags.get('tags'), {'c7n': 'True', 'abcd': 'xyz'})


class ConnectPhoneNumberTest(BaseTest):
    def test_connect_phone_number_query(self):
        session_factory = self.replay_flight_data("test_connect_phone_number_query")
        p = self.load_policy(
            {
                "name": "connect-phone-number-query-test",
                "resource": "connect-phone-number"
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connect_phone_number_tagging(self):
        session_factory = self.replay_flight_data("test_connect_phone_number_tagging")
        client = session_factory().client("connect")

        p = self.load_policy(
            {
                "name": "connect-phone-number-mark-for-op-test",
                "resource": "connect-phone-number",
                "filters": [{'tag:c7n': 'True'}],
                'actions': [{
                    'type': 'mark-for-op',
                    'tag': 'custodian_cleanup',
                    'op': 'notify',
                    'days': 4
                }]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "connect-phone-number-tag-test",
                "resource": "connect-phone-number",
                "filters": [
                    {'tag:custodian_cleanup': 'Resource does not meet policy: notify@2022/09/19'}
                ],
                "actions": [
                    {"type": "tag", "key": "abcd", "value": "xyz"},
                    {"type": "remove-tag", "tags": ["custodian_cleanup"]},
                ],
            }, session_factory=session_factory
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        arn = resources[0]['PhoneNumberArn']
        tags = client.list_tags_for_resource(resourceArn=arn)
        self.assertEqual(tags.get('tags'), {'c7n': 'True', 'abcd': 'xyz'})
