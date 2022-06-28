# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Google Queue Message Processing
==============================

"""
import base64
import json
import zlib

import six
from c7n_mailer.email_delivery import EmailDelivery

try:
    from c7n_gcp.client import Session
except ImportError:
    raise Exception("Using GCP Pub/Sub with c7n_mailer requires package c7n_gcp to be installed.")

MAX_MESSAGES = 1000


class MailerGcpQueueProcessor(object):
    def __init__(self, config, logger, session=None):
        self.config = config
        self.logger = logger
        self.subscription = self.config["queue_url"]
        self.session = session or Session()
        self.client = self.session.client("pubsub", "v1", "projects.subscriptions")

    def run(self):
        self.logger.info("Downloading messages from the GCP PubSub Subscription.")

        # Get first set of messages to process
        messages = self.receive_messages()

        while len(messages['receivedMessages']) > 0:
            # Discard_date is the timestamp of the last published message in the messages list
            # and will be the date we need to seek to when we ack_messages
            discard_date = messages["receivedMessages"][-1]["message"]["publishTime"]

            # Process received messages
            for message in messages["receivedMessages"]:
                self.process_message(message)

            # Acknowledge and purge processed messages then get next set of messages
            self.ack_messages(discard_date)
            messages = self.receive_messages()

        self.logger.info("No messages left in the gcp topic subscription, now exiting c7n_mailer.")

    # This function, when processing gcp pubsub messages, will deliver messages over email.
    # Also support for Datadog and Slack
    def process_message(self, encoded_gcp_pubsub_message):
        pubsub_message = self.unpack_to_dict(encoded_gcp_pubsub_message["message"]["data"])
        # Process email first
        delivery = EmailDelivery(self.config, self.session, self.logger)
        to_email_messages_map = delivery.get_to_addrs_email_messages_map(pubsub_message)
        for email_to_addrs, mimetext_msg in six.iteritems(to_email_messages_map):
            delivery.send_c7n_email(pubsub_message, list(email_to_addrs), mimetext_msg)
        # Process Datadog
        if any(e.startswith("datadog") for e in pubsub_message.get("action", ()).get("to")):
            self._deliver_datadog_message(pubsub_message)
        # Process Slack
        if any(
            e.startswith("slack") or e.startswith("https://hooks.slack.com/")
            for e in pubsub_message.get("action", ()).get("to")
        ):
            self._deliver_slack_message(pubsub_message, delivery)
        return True

    def _deliver_datadog_message(self, pubsub_message):
        from c7n_mailer.datadog_delivery import DataDogDelivery

        datadog_delivery = DataDogDelivery(self.config, self.session, self.logger)
        datadog_message_packages = datadog_delivery.get_datadog_message_packages(pubsub_message)

        try:
            self.logger.info("Sending message to Datadog.")
            datadog_delivery.deliver_datadog_messages(datadog_message_packages, pubsub_message)
            return True
        except Exception as error:
            self.logger.exception(error)
            pass

    def _deliver_slack_message(self, pubsub_message, email_handler):
        from c7n_mailer.slack_delivery import SlackDelivery

        slack_delivery = SlackDelivery(self.config, self.logger, email_handler)
        slack_messages = slack_delivery.get_to_addrs_slack_messages_map(pubsub_message)
        try:
            self.logger.info("Sending message to Slack.")
            slack_delivery.slack_handler(pubsub_message, slack_messages)
            return True
        except Exception as error:
            self.logger.exception(error)
            pass

    def receive_messages(self):
        """Receive messsage(s) from subscribed topic"""
        return self.client.execute_command(
            "pull",
            {
                "subscription": self.subscription,
                "body": {"returnImmediately": True, "max_messages": MAX_MESSAGES},
            },
        )

    def ack_messages(self, discard_datetime):
        """Acknowledge and Discard messages up to datetime using seek api command"""
        return self.client.execute_command(
            "seek", {"subscription": self.subscription, "body": {"time": discard_datetime}}
        )

    @staticmethod
    def unpack_to_dict(encoded_gcp_pubsub_message):
        """Returns a message as a dict that been base64 decoded"""
        return json.loads(zlib.decompress(base64.b64decode(encoded_gcp_pubsub_message)))
