# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import unittest
import copy
import json
import os
from mock import patch, MagicMock

from common import RESOURCE_3, SQS_MESSAGE_5

from c7n_mailer.slack_delivery import SlackDelivery
from c7n_mailer.email_delivery import EmailDelivery

SLACK_TOKEN = "slack-token"
SLACK_POST_MESSAGE_API = "https://slack.com/api/chat.postMessage"


class TestSlackDelivery(unittest.TestCase):
    def setUp(self):
        self.config = {
            "slack_token": SLACK_TOKEN,
            "templates_folders": [
                os.path.abspath(os.path.dirname(__file__)),
                os.path.abspath("/"),
                os.path.join(os.path.abspath(os.path.dirname(__file__)), "test-templates/"),
            ],
        }

        self.session = MagicMock()
        self.logger = MagicMock()

        self.email_delivery = EmailDelivery(self.config, self.session, self.logger)
        self.message = copy.deepcopy(SQS_MESSAGE_5)
        self.resource = copy.deepcopy(RESOURCE_3)
        self.message["resources"] = [self.resource]
        self.target_channel = "test-channel"

    def test_map_sending_to_channel(self):
        slack = SlackDelivery(self.config, self.logger, self.email_delivery)
        result = slack.get_to_addrs_slack_messages_map(self.message)

        assert self.target_channel in result
        assert json.loads(result[self.target_channel])["channel"] == self.target_channel

    def test_map_sending_to_tag_channel_with_hash(self):
        self.target_channel = "#tag-channel"
        slack = SlackDelivery(self.config, self.logger, self.email_delivery)
        message_destination = ["slack://tag/SlackChannel"]

        self.resource["Tags"].append({"Key": "SlackChannel", "Value": self.target_channel})
        self.message["action"]["to"] = message_destination
        self.message["policy"]["actions"][1]["to"] = message_destination

        result = slack.get_to_addrs_slack_messages_map(self.message)

        assert self.target_channel in result
        assert json.loads(result[self.target_channel])["channel"] == self.target_channel
        self.logger.debug.assert_called_with("Generating message for specified Slack channel.")

    def test_map_sending_to_tag_channel_without_hash(self):
        self.target_channel = "tag-channel"
        channel_name = "#" + self.target_channel

        slack = SlackDelivery(self.config, self.logger, self.email_delivery)
        message_destination = ["slack://tag/SlackChannel"]

        self.resource["Tags"].append({"Key": "SlackChannel", "Value": self.target_channel})
        self.message["action"]["to"] = message_destination
        self.message["policy"]["actions"][1]["to"] = message_destination

        result = slack.get_to_addrs_slack_messages_map(self.message)

        assert channel_name in result
        assert json.loads(result[channel_name])["channel"] == channel_name
        self.logger.debug.assert_called_with("Generating message for specified Slack channel.")

    def test_map_sending_to_tag_channel_no_tag(self):
        slack = SlackDelivery(self.config, self.logger, self.email_delivery)

        message_destination = ["slack://tag/SlackChannel"]
        self.message["action"]["to"] = message_destination
        self.message["policy"]["actions"][1]["to"] = message_destination

        result = slack.get_to_addrs_slack_messages_map(self.message)

        assert result == {}
        self.logger.debug.assert_called_with("No SlackChannel tag found in resource.")

    def test_map_sending_to_webhook(self):
        webhook = "https://hooks.slack.com/this-is-a-webhook"

        slack = SlackDelivery(self.config, self.logger, self.email_delivery)

        message_destination = [webhook]
        self.message["action"]["to"] = message_destination
        self.message["policy"]["actions"][1]["to"] = message_destination

        result = slack.get_to_addrs_slack_messages_map(self.message)

        assert webhook in result
        assert "channel" not in json.loads(result[webhook])

    @patch("c7n_mailer.slack_delivery.requests.post")
    def test_slack_handler(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}

        slack = SlackDelivery(self.config, self.logger, self.email_delivery)
        result = slack.get_to_addrs_slack_messages_map(self.message)
        slack.slack_handler(self.message, result)

        self.logger.info.assert_called_with(
            "Sending account:core-services-dev "
            "policy:ebs-mark-unattached-deletion ebs:1 slack:slack"
            "_default to test-channel"
        )

    @patch("c7n_mailer.slack_delivery.requests.post")
    def test_send_slack_msg_webhook(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}

        webhook = "https://hooks.slack.com/this-is-a-webhook"
        message_destination = [webhook]

        self.message["action"]["to"] = message_destination
        self.message["policy"]["actions"][1]["to"] = message_destination

        slack = SlackDelivery(self.config, self.logger, self.email_delivery)
        result = slack.get_to_addrs_slack_messages_map(self.message)
        slack.send_slack_msg(webhook, result[webhook])

        _, kwargs = mock_post.call_args
        assert webhook == kwargs["url"]
        assert kwargs["data"] == result[webhook]

    @patch("c7n_mailer.slack_delivery.requests.post")
    def test_send_slack_msg(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}

        slack = SlackDelivery(self.config, self.logger, self.email_delivery)
        result = slack.get_to_addrs_slack_messages_map(self.message)
        slack.send_slack_msg(self.target_channel, result[self.target_channel])

        _, kwargs = mock_post.call_args
        assert self.target_channel == json.loads(kwargs["data"])["channel"]
        assert SLACK_POST_MESSAGE_API == kwargs["url"]
        assert kwargs["data"] == result[self.target_channel]

    @patch("c7n_mailer.slack_delivery.requests.post")
    def test_send_slack_msg_retry_after(self, mock_post):
        retry_after_delay = 1
        mock_post.return_value.status_code = 429
        mock_post.return_value.headers = {"Retry-After": retry_after_delay}

        slack = SlackDelivery(self.config, self.logger, self.email_delivery)
        result = slack.get_to_addrs_slack_messages_map(self.message)
        slack.send_slack_msg(self.target_channel, result[self.target_channel])

        self.logger.info.assert_called_with(
            "Slack API rate limiting. Waiting %d seconds", retry_after_delay
        )

    @patch("c7n_mailer.slack_delivery.requests.post")
    def test_send_slack_msg_not_200_response(self, mock_post):
        mock_post.return_value.status_code = 404
        mock_post.return_value.text = "channel_not_found"

        slack = SlackDelivery(self.config, self.logger, self.email_delivery)
        result = slack.get_to_addrs_slack_messages_map(self.message)
        slack.send_slack_msg(self.target_channel, result[self.target_channel])

        self.logger.info.assert_called_with(
            "Error in sending Slack message status:%s response: %s", 404, "channel_not_found"
        )

    @patch("c7n_mailer.slack_delivery.requests.post")
    def test_send_slack_msg_not_ok_response(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": False, "error": "failed"}

        slack = SlackDelivery(self.config, self.logger, self.email_delivery)
        result = slack.get_to_addrs_slack_messages_map(self.message)
        slack.send_slack_msg(self.target_channel, result[self.target_channel])

        self.logger.info.assert_called_with(
            "Error in sending Slack message. Status:%s, " "response:%s", 200, "failed"
        )
