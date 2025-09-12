# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import traceback

from .email_delivery import EmailDelivery
from .utils import decrypt


class MessageTargetMixin(object):
    def handle_targets(self, message, sent_timestamp, email_delivery=True, sns_delivery=False):
        # get the map of email_to_addresses to mimetext messages (with resources baked in)
        # and send any emails (to SES or SMTP) if there are email addresses found
        if email_delivery:
            email_delivery = EmailDelivery(self.config, self.session, self.logger)
            email_delivery.send_c7n_email(message)

        # this sections gets the map of sns_to_addresses to rendered_jinja messages
        # (with resources baked in) and delivers the message to each sns topic
        if sns_delivery:
            from .sns_delivery import SnsDelivery

            sns_delivery = SnsDelivery(self.config, self.session, self.logger)
            sns_message_packages = sns_delivery.get_sns_message_packages(message)
            sns_delivery.deliver_sns_messages(sns_message_packages, message)

        # this section sends a notification to the resource owner via Slack
        if any(
            e.startswith("slack") or e.startswith("https://hooks.slack.com/")
            for e in message.get("action", {}).get("to", [])
            + message.get("action", {}).get("owner_absent_contact", [])
        ):
            from .slack_delivery import SlackDelivery

            if self.config.get("slack_token"):
                self.config["slack_token"] = decrypt(
                    self.config, self.logger, self.session, "slack_token"
                ).strip()

            slack_delivery = SlackDelivery(self.config, self.logger, email_delivery)
            slack_messages = slack_delivery.get_to_addrs_slack_messages_map(message)
            try:
                slack_delivery.slack_handler(message, slack_messages)
            except Exception:
                traceback.print_exc()
                pass

        # this section gets the map of metrics to send to datadog and delivers it
        if any(e.startswith("datadog") for e in message.get("action", ()).get("to")):
            from .datadog_delivery import DataDogDelivery

            datadog_delivery = DataDogDelivery(self.config, self.session, self.logger)
            datadog_message_packages = datadog_delivery.get_datadog_message_packages(message)

            try:
                datadog_delivery.deliver_datadog_messages(datadog_message_packages, message)
            except Exception:
                traceback.print_exc()
                pass

        # this section sends the full event to a Splunk HTTP Event Collector (HEC)
        if any(e.startswith("splunkhec://") for e in message.get("action", ()).get("to")):
            from .splunk_delivery import SplunkHecDelivery

            splunk_delivery = SplunkHecDelivery(self.config, self.session, self.logger)
            splunk_messages = splunk_delivery.get_splunk_payloads(message, sent_timestamp)

            try:
                splunk_delivery.deliver_splunk_messages(splunk_messages)
            except Exception:
                traceback.print_exc()
                pass
