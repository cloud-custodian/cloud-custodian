# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import boto3
import copy
import os
import unittest

from c7n_mailer.email_delivery import EmailDelivery
from common import (
    logger,
    get_ldap_lookup,
    GCP_SMTP_MESSAGE,
    MAILER_CONFIG,
    MAILER_CONFIG_GCP,
    RESOURCE_1,
    RESOURCE_4,
    SQS_MESSAGE_1,
    SQS_MESSAGE_4,
)
from mock import patch, call, MagicMock

from c7n_mailer.utils_email import is_email, priority_header_is_valid, get_mimetext_message

# note principalId is very org/domain specific for federated?, it would be good to get
# confirmation from capone on this event / test.
CLOUDTRAIL_EVENT = {
    "detail": {
        "userIdentity": {
            "type": "IAMUser",
            "principalId": "AIDAJ45Q7YFFAREXAMPLE",
            "arn": "arn:aws:iam::123456789012:user/michael_bolton",
            "accountId": "123456789012",
            "accessKeyId": "AKIAIOSFODNN7EXAMPLE",
            "userName": "michael_bolton",
        }
    }
}


class MockEmailDelivery(EmailDelivery):
    def get_ldap_connection(self):
        return get_ldap_lookup(cache_engine="redis")


class EmailTest(unittest.TestCase):
    def setUp(self):
        self.aws_session = boto3.Session()
        self.email_delivery = MockEmailDelivery(MAILER_CONFIG, self.aws_session, logger)
        self.email_delivery.ldap_lookup.uid_regex = ""
        template_abs_filename = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "example.jinja"
        )

        # Jinja paths must always be forward slashes regardless of operating system
        template_abs_filename = template_abs_filename.replace("\\", "/")

        SQS_MESSAGE_1["action"]["template"] = template_abs_filename
        SQS_MESSAGE_4["action"]["template"] = template_abs_filename

    def test_valid_email(self):
        self.assertFalse(is_email("foobar"))
        self.assertFalse(is_email("foo@bar"))
        self.assertFalse(is_email("slack://foo@bar.com"))
        self.assertTrue(is_email("foo@bar.com"))

    def test_smtp_creds(self):
        conf = dict(MAILER_CONFIG)
        conf["smtp_username"] = "alice"
        conf["smtp_password"] = "bob"

        msg = dict(SQS_MESSAGE_1)
        deliver = MockEmailDelivery(conf, self.aws_session, logger)

        with patch("smtplib.SMTP") as mock_smtp:
            with patch("c7n_mailer.utils.kms_decrypt") as mock_decrypt:
                mock_decrypt.return_value = "xyz"
                deliver.send_c7n_email(msg)
            mock_decrypt.assert_called_once()
            mock_smtp.assert_has_calls([call().login("alice", "xyz")])

    def test_kms_not_called_for_gcp(self):
        conf = dict(MAILER_CONFIG_GCP)
        conf["smtp_username"] = "alice"
        conf["smtp_password"] = "bob"

        msg = dict(GCP_SMTP_MESSAGE)
        deliver = MockEmailDelivery(conf, self.aws_session, logger)
        messages_map = deliver.get_emails_to_mimetext_map(msg)

        with patch("smtplib.SMTP") as mock_smtp:
            with patch("c7n_mailer.utils.kms_decrypt") as mock_decrypt:
                # mock_decrypt.return_value = "xyz"
                print(messages_map)
                deliver.send_c7n_email(msg)
            mock_decrypt.assert_not_called()
            mock_smtp.assert_has_calls([call().login("alice", "bob")])

    def test_priority_header_is_valid(self):
        self.assertFalse(priority_header_is_valid("0", self.email_delivery.logger))
        self.assertFalse(priority_header_is_valid("-1", self.email_delivery.logger))
        self.assertFalse(priority_header_is_valid("6", self.email_delivery.logger))
        self.assertFalse(priority_header_is_valid("sd", self.email_delivery.logger))
        self.assertTrue(priority_header_is_valid("1", self.email_delivery.logger))
        self.assertTrue(priority_header_is_valid("5", self.email_delivery.logger))

    def test_get_valid_emails_from_list(self):
        list_1 = [
            "michael_bolton@initech.com",
            "lsdk",
            "resource-owner",
            "event-owner",
            "bill@initech.com",
        ]
        valid_emails = self.email_delivery.get_valid_emails_from_list(list_1)
        self.assertEqual(valid_emails, ["michael_bolton@initech.com", "bill@initech.com"])

    def test_event_owner_ldap_flow(self):
        targets = ["event-owner"]
        michael_bolton_email = self.email_delivery.get_event_owner_email(targets, CLOUDTRAIL_EVENT)
        self.assertEqual(michael_bolton_email, ["michael_bolton@initech.com"])

    def test_get_ldap_emails_from_resource(self):
        SQS_MESSAGE_1["action"]["email_ldap_username_manager"] = False
        ldap_emails = self.email_delivery.get_ldap_emails_from_resource(SQS_MESSAGE_1, RESOURCE_1)
        self.assertEqual(ldap_emails, ["peter@initech.com"])
        SQS_MESSAGE_1["action"]["email_ldap_username_manager"] = True
        ldap_emails = self.email_delivery.get_ldap_emails_from_resource(SQS_MESSAGE_1, RESOURCE_1)
        self.assertEqual(ldap_emails, ["peter@initech.com", "bill_lumberg@initech.com"])

    def test_email_to_resources_map_with_ldap_manager(self):
        emails_to_resources_map = self.email_delivery.get_emails_to_resources_map(SQS_MESSAGE_1)
        # make sure only 1 email is queued to go out
        self.assertEqual(len(emails_to_resources_map.items()), 1)
        to_emails = ("bill_lumberg@initech.com", "milton@initech.com", "peter@initech.com")
        self.assertEqual(emails_to_resources_map, {to_emails: [RESOURCE_1]})

    def test_email_to_email_message_map_without_ldap_manager(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE["policy"]["actions"][1].pop("email_ldap_username_manager", None)
        email_addrs_to_email_message_map = self.email_delivery.get_emails_to_mimetext_map(
            SQS_MESSAGE
        )
        to_emails = ("bill_lumberg@initech.com", "milton@initech.com", "peter@initech.com")
        items = list(email_addrs_to_email_message_map.items())
        self.assertEqual(items[0][0], to_emails)
        self.assertEqual(items[0][1]["to"], ", ".join(to_emails))

    def test_email_to_email_message_map_additional_headers(self):
        conf = dict(MAILER_CONFIG)
        conf["additional_email_headers"] = {"X-Foo": "X-Foo-Value", "X-Bar": "1234"}
        email_delivery = MockEmailDelivery(conf, self.aws_session, logger)
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE["policy"]["actions"][1].pop("email_ldap_username_manager", None)
        email_addrs_to_email_message_map = email_delivery.get_emails_to_mimetext_map(SQS_MESSAGE)
        for _, mimetext_msg in email_addrs_to_email_message_map.items():
            self.assertEqual(mimetext_msg["X-Foo"], "X-Foo-Value")
            self.assertEqual(mimetext_msg["X-Bar"], "1234")

    def test_smtp_called_once(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        to_addrs_to_email_messages_map = self.email_delivery.get_emails_to_mimetext_map(SQS_MESSAGE)
        with patch("smtplib.SMTP") as mock_smtp:
            self.email_delivery.send_c7n_email(SQS_MESSAGE)
            for mimetext_msg in to_addrs_to_email_messages_map.values():
                self.assertEqual(mimetext_msg["X-Priority"], "1 (Highest)")

            # Get instance of mocked SMTP object
            smtp_instance = mock_smtp.return_value
            # Checks the mock has been called at least one time
            self.assertTrue(smtp_instance.sendmail.called)
            # Check the mock has been called only once
            self.assertEqual(smtp_instance.sendmail.call_count, 1)
            # Check the mock' calls are equal to a specific list of calls in a
            # specific order
            to_addrs = ["bill_lumberg@initech.com", "milton@initech.com", "peter@initech.com"]
            self.assertEqual(
                smtp_instance.sendmail.mock_calls,
                [call(MAILER_CONFIG["from_address"], to_addrs, mimetext_msg.as_string())],
            )

    def test_smtp_called_multiple_times(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE["action"].pop("priority_header", None)
        RESOURCE_2 = {
            "AvailabilityZone": "us-east-1a",
            "Attachments": [],
            "Tags": [{"Value": "samir@initech.com", "Key": "SupportEmail"}],
            "VolumeId": "vol-01a0e6ea6b8lsdkj93",
        }
        SQS_MESSAGE["resources"].append(RESOURCE_2)
        to_addrs_to_email_messages_map = self.email_delivery.get_emails_to_mimetext_map(SQS_MESSAGE)
        with patch("smtplib.SMTP") as mock_smtp:
            self.email_delivery.send_c7n_email(SQS_MESSAGE)
            for mimetext_msg in to_addrs_to_email_messages_map.values():
                self.assertEqual(mimetext_msg.get("X-Priority"), None)
                # self.assertEqual(mimetext_msg.get('X-Priority'), None)
            # Get instance of mocked SMTP object
            smtp_instance = mock_smtp.return_value
            # Checks the mock has been called at least one time
            self.assertTrue(smtp_instance.sendmail.called)
            # Check the mock has been called only once
            self.assertEqual(smtp_instance.sendmail.call_count, 2)

    def test_emails_resource_mapping_multiples(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE["action"].pop("priority_header", None)
        RESOURCE_2 = {
            "AvailabilityZone": "us-east-1a",
            "Attachments": [],
            "Tags": [{"Value": "samir@initech.com", "Key": "SupportEmail"}],
            "VolumeId": "vol-01a0e6ea6b8lsdkj93",
        }
        SQS_MESSAGE["resources"].append(RESOURCE_2)
        emails_to_resources_map = self.email_delivery.get_emails_to_resources_map(SQS_MESSAGE)
        email_1_to_addrs = ("bill_lumberg@initech.com", "milton@initech.com", "peter@initech.com")
        email_2_to_addrs = ("samir@initech.com",)
        self.assertEqual(emails_to_resources_map[email_1_to_addrs], [RESOURCE_1])
        self.assertEqual(emails_to_resources_map[email_2_to_addrs], [RESOURCE_2])

    def test_emails_resource_mapping_no_owner(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE["action"].pop("priority_header", None)
        SQS_MESSAGE["action"]["owner_absent_contact"] = ["foo@example.com"]
        RESOURCE_2 = {
            "AvailabilityZone": "us-east-1a",
            "Attachments": [],
            "Tags": [{"Value": "peter", "Key": "CreatorName"}],
            "VolumeId": "vol-01a0e6ea6b89f0099",
        }
        SQS_MESSAGE["resources"] = [RESOURCE_2]
        emails_to_resources_map = self.email_delivery.get_emails_to_resources_map(SQS_MESSAGE)
        email_1_to_addrs = ("bill_lumberg@initech.com", "foo@example.com", "peter@initech.com")
        self.assertEqual(emails_to_resources_map[email_1_to_addrs], [RESOURCE_2])

    def test_no_mapping_if_no_valid_emails(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE["action"].get("to", []).remove("ldap_uid_tags")
        SQS_MESSAGE["resources"][0].pop("Tags", None)
        emails_to_resources_map = self.email_delivery.get_emails_to_resources_map(SQS_MESSAGE)
        self.assertEqual(emails_to_resources_map, {})

    def test_flattened_list_get_resource_owner_emails_from_resource(self):
        RESOURCE_2 = {
            "AvailabilityZone": "us-east-1a",
            "Attachments": [],
            "Tags": [{"Value": "123456", "Key": "OwnerEmail"}],
            "VolumeId": "vol-01a0e6ea6b8lsdkj93",
        }
        RESOURCE_3 = {
            "AvailabilityZone": "us-east-1a",
            "Attachments": [],
            "Tags": [{"Value": "milton@initech.com", "Key": "OwnerEmail"}],
            "VolumeId": "vol-01a0e6ea6b8lsdkj93",
        }

        ldap_emails = self.email_delivery.get_resource_owner_emails_from_resource(
            SQS_MESSAGE_1, RESOURCE_2
        )

        self.assertEqual(ldap_emails, ["milton@initech.com"])

        ldap_emails = self.email_delivery.get_resource_owner_emails_from_resource(
            SQS_MESSAGE_1, RESOURCE_3
        )

        self.assertEqual(ldap_emails, ["milton@initech.com"])

    def test_get_resource_owner_emails_from_resource_org_domain_not_invoked(self):
        config = copy.deepcopy(MAILER_CONFIG)
        logger_mock = MagicMock()

        # Enable org_domain
        config["org_domain"] = "test.com"

        # Add "CreatorName" to contact tags to avoid creating a new
        # resource.
        config["contact_tags"].append("CreatorName")

        self.email_delivery = MockEmailDelivery(config, self.aws_session, logger_mock)
        org_emails = self.email_delivery.get_resource_owner_emails_from_resource(
            SQS_MESSAGE_1, RESOURCE_1
        )

        assert org_emails == ["milton@initech.com", "peter@initech.com"]
        assert (
            call("Using org_domain to reconstruct email addresses from contact_tags values")
            not in logger_mock.debug.call_args_list
        )

    def test_get_resource_owner_emails_from_resource_org_domain(self):
        config = copy.deepcopy(MAILER_CONFIG)
        logger_mock = MagicMock()

        # Enable org_domain and disable ldap lookups
        # If ldap lookups are enabled, org_domain logic is not invoked.
        config["org_domain"] = "test.com"
        del config["ldap_uri"]

        # Add "CreatorName" to contact tags to avoid creating a new
        # resource.
        config["contact_tags"].append("CreatorName")

        self.email_delivery = MockEmailDelivery(config, self.aws_session, logger_mock)
        org_emails = self.email_delivery.get_resource_owner_emails_from_resource(
            SQS_MESSAGE_1, RESOURCE_1
        )

        assert org_emails == ["milton@initech.com", "peter@test.com"]
        logger_mock.debug.assert_called_with(
            "Using org_domain to reconstruct email addresses from contact_tags values"
        )

    def test_cc_email_functionality(self):
        email = get_mimetext_message(
            self.email_delivery.config,
            self.email_delivery.logger,
            SQS_MESSAGE_4,
            SQS_MESSAGE_4["resources"],
            ["hello@example.com"],
        )
        self.assertEqual(email["Cc"], "hello@example.com, cc@example.com")

    def test_sendgrid(self):
        config = copy.deepcopy(MAILER_CONFIG)
        logger_mock = MagicMock()

        config["sendgrid_api_key"] = "SENDGRID_API_KEY"
        del config["smtp_server"]

        delivery = MockEmailDelivery(config, self.aws_session, logger_mock)

        with patch("sendgrid.SendGridAPIClient.send") as mock_send:
            with patch("c7n_mailer.utils.kms_decrypt") as mock_decrypt:
                mock_decrypt.return_value = "xyz"
                delivery.send_c7n_email(SQS_MESSAGE_1)
                mock_decrypt.assert_called_once()
            mock_send.assert_called()
            # NOTE send to 3 addrs: bill_lumberg@initech.com,milton@initech.com,peter@initech.com
            assert mock_send.call_count == 3

        # NOTE reproduce duplicated emails bug when len(emails_to_mimetext_map) > 1
        sqs_msg = copy.deepcopy(SQS_MESSAGE_1)
        sqs_msg["resources"].append(RESOURCE_4)
        with patch("sendgrid.SendGridAPIClient.send") as mock_send:
            with patch("c7n_mailer.utils.kms_decrypt") as mock_decrypt:
                mock_decrypt.return_value = "xyz"
                delivery.send_c7n_email(sqs_msg)
            # ensure send 4 times instead of 8 as there are only 4 addrs
            assert mock_send.call_count == 4

    def test_ms_graph(self):
        config = copy.deepcopy(MAILER_CONFIG)
        logger_mock = MagicMock()

        del config["smtp_server"]
        config.update(
            {
                "graph_sendmail_endpoint": "my_graph_sendmail_endpoint",
                "graph_token_endpoint": "my_graph_token_endpoint",
                "graph_client_id": "graph_client_id",
                "graph_client_secret": "graph_client_secret",
            }
        )

        delivery = MockEmailDelivery(config, self.aws_session, logger_mock)

        with patch("requests.post") as req:
            with patch("c7n_mailer.utils.kms_decrypt") as mock_decrypt:
                mock_decrypt.return_value = "xyz"
                delivery.send_c7n_email(SQS_MESSAGE_1)
                mock_decrypt.assert_called_once()

            assert req.call_count == 2
            token_req = req.call_args_list[0]
            assert token_req[0][0] == "my_graph_token_endpoint"
            assert token_req[1]["data"]["client_secret"] == "xyz"
            sendmail_req = req.call_args_list[1]
            assert sendmail_req[0][0] == "my_graph_sendmail_endpoint"
            assert sendmail_req[1]["data"].startswith(
                '{"message": {"subject": "core-services-dev AWS EBS Volumes'
                ' will be DELETED in 15 DAYS!"'
            )

    def test_ses_send_raw_email(self):
        config = copy.deepcopy(MAILER_CONFIG)
        logger_mock = MagicMock()

        del config["smtp_server"]
        delivery = MockEmailDelivery(config, self.aws_session, logger_mock)

        sqs_msg = copy.deepcopy(SQS_MESSAGE_1)
        sqs_msg["resources"].append(RESOURCE_4)
        with patch("botocore.client.BaseClient._make_api_call") as mock_send:
            delivery.send_c7n_email(sqs_msg)
            # Ensure the for loop is working by checking the call_count
            assert mock_send.call_count == 2
            args = mock_send.call_args_list[0][0]
            assert args[0] == "SendRawEmail"
            assert "To: bill_lumberg@initech.com" in args[1]["RawMessage"]["Data"]
            args = mock_send.call_args_list[1][0]
            assert "To: someone@example.com" in args[1]["RawMessage"]["Data"]

    def test_get_ldap_connection(self):
        with patch("c7n_mailer.email_delivery.decrypt") as patched:
            patched.return_value = "a password"
            delivery = EmailDelivery({"ldap_uri": "foo"}, self.aws_session, MagicMock())
            patched.assert_called()
            self.assertEqual(delivery.config["ldap_bind_password"], "a password")

    def test_get_valid_emails_from_list_gcp(self):
        delivery = EmailDelivery(
            {"ldap_uri": "foo", "email_base_url": "example.com"}, self.aws_session, MagicMock()
        )
        result = delivery.get_valid_emails_from_list(["resource-owner", "foo:bar"])
        self.assertEqual(len(result), 2)
        self.assertTrue("foo@example.com" in result)
        self.assertTrue("bar@example.com" in result)
