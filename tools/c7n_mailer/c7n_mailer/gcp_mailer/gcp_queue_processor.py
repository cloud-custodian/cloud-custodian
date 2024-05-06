# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Google Queue Message Processing
==============================

"""
import base64
import json
import zlib

from c7n_mailer.target import MessageTargetMixin

try:
    from c7n_gcp.client import Session
except ImportError:
    raise ImportError(
        "c7n-mailer is configured for GCP Pub/Sub, which requires additional packages. "
        "Run 'pip install c7n-mailer[gcp]' to install them."
    )

MAX_MESSAGES = 1000


class MailerGcpQueueProcessor(MessageTargetMixin):
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

        while messages and len(messages["receivedMessages"]) > 0:
            # Discard_date is the timestamp of the last published message in the messages list
            # and will be the date we need to seek to when we ack_messages
            discard_date = messages["receivedMessages"][-1]["message"]["publishTime"]

            # Process received messages
            for message in messages["receivedMessages"]:
                self.process_message(message, discard_date)

            # Acknowledge and purge processed messages then get next set of messages
            self.ack_messages(discard_date)
            messages = self.receive_messages()

        self.logger.info("No messages left in the gcp topic subscription, now exiting c7n_mailer.")

    # This function, when processing gcp pubsub messages, will deliver messages over email.
    # Also support for Datadog and Slack
    def process_message(self, encoded_gcp_pubsub_message, publish_date):
        pubsub_message = self.unpack_to_dict(encoded_gcp_pubsub_message["message"]["data"])
        self.handle_targets(pubsub_message, publish_date, email_delivery=True, sns_delivery=False)
        return True

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
