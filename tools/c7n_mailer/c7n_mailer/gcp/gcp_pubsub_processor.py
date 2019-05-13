# Copyright 2019 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
GCP Pub-Sub Message Processing
==============================
"""

import six
from c7n_mailer.email_delivery import EmailDelivery
import base64
import zlib


class MailerGcpPubSubProcessor(object):

    def __init__(self, config, logger, session=None):
        self.config = config
        self.logger = logger
        self.subscription = self.config['queue_url']
        self.session = session

    def run(self):
        self.logger.info("Downloading messages from the GCP PubSub Subscription.")

        # Get first set of messages to process
        messages = self.receive_messages()

        while len(messages) > 0:
            # Discard_date is the timestamp of the last published message in the messages list
            # and will be the date we need to seek to when we ack_messages
            discard_date = messages['receivedMessages'][-1]['message']['publishTime']

            # Process received messages
            for message in messages['receivedMessages']:
                self.process_message(message)

            # Acknowledge and purge processed messages then get next set of messages
            self.ack_messages(discard_date)
            messages = self.receive_messages()

        self.logger.info('No messages left in the gcp topic subscription, now exiting c7n_mailer.')

    # This function, when processing gcp pubsub messages, will only deliver messages over email.
    # TODO: Slack and Datadog integration or wait for future redesign
    def process_message(self, encoded_gcp_pubsub_message):
        pubsub_message = self.unpack(encoded_gcp_pubsub_message['message']['data'])
        delivery = EmailDelivery(self.config, self.session, self.logger)
        to_email_messages_map = delivery.get_to_addrs_email_messages_map(
            pubsub_message)
        for email_to_addrs, mimetext_msg in six.iteritems(to_email_messages_map):
            delivery.send_c7n_email(pubsub_message, list(email_to_addrs), mimetext_msg)

    def receive_messages(self):
        """Receive messsage(s) from subscribed topic
        """
        client = self.session.client('pubsub', 'v1', 'projects.subscriptions')

        return client.execute_command('pull', {
            'subscription': self.subscription,
            'body': {
                'returnImmediately': True
            }
        })

    def ack_messages(self, discard_datetime):
        """Acknowledge and Discard messages up to datetime using seek api command
        """
        client = self.session.client('pubsub', 'v1', 'projects.subscriptions')

        return client.execute_command('seek', {
            'subscription': self.subscription,
            'body': {
                'time': discard_datetime
            }
        })

    @staticmethod
    def unpack(encoded_gcp_pubsub_message):
        """ Returns a message that been base64 decoded
        """
        b64decoded = base64.b64decode(encoded_gcp_pubsub_message)
        uncompressed = zlib.decompress(b64decoded)
        return uncompressed
