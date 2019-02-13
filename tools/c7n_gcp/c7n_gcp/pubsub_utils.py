# Copyright 2018 Capital One Services, LLC
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


from googleapiclient.errors import HttpError
import base64
import zlib
from datetime import tzinfo, timedelta
from c7n import utils

MAX_MESSAGES = 200


class PubSubUtilities(object):
    """Utility Class for C&N GCP Pub Sub functionality
    An example use-case for this class is as follows:
    Publish messages to GCP Pub/Sub Service:
    C7N_GCP NotifyAction class uses this utility class to connect to Topics
    and publish messages(send messages to the GCP Pub/Sub Service)

    Receive messages from GCP Pub/Sub Service:
    C7N_GCP-Mailer Processor class uses this utility class to connect to subscriptions
    to receive messages.
    """

    """
    Class methods for Pub/Sub message handling
    """
    @staticmethod
    def publish_message(session, data, message):
        """Publish message to a GCP pub/sub topic
         """
        topic = PubSubUtilities.ensure_topic(session, data)

        client = session.client('pubsub', 'v1', 'projects.topics')

        try:
            return client.execute_command('publish', {
                'topic': topic,
                'body': {
                    'messages': {
                        'data': PubSubUtilities.pack(message)
                    }
                }
            })
        except HttpError as e:
            if e.resp.status != 404:
                raise

    @staticmethod
    def receive_messages(session, subscription, max_messages=None):
        """Receive messsage(s) from subscribed topic
        """
        subscriber_param = PubSubUtilities.get_subscription_param(session, subscription)

        client = session.client('pubsub', 'v1', 'projects.subscriptions')
        try:
            return client.execute_command('pull', {
                'subscription': subscriber_param,
                'body': {
                    'returnImmediately': True,
                    'maxMessages': max_messages or MAX_MESSAGES

                }
            })
        except HttpError as e:
            if e.resp.status != 404:
                raise

        pass

    @staticmethod
    def ack_messages(session, discard_datetime, subscription):
        """Acknowledge and Discard messages up to datetime using seek api command
        """
        subscriber_param = PubSubUtilities.get_subscription_param(session, subscription)

        client = session.client('pubsub', 'v1', 'projects.subscriptions')
        try:
            return client.execute_command('seek', {
                'subscription': subscriber_param,
                'body': {
                    'time': discard_datetime
                }
            })
        except HttpError as e:
            if e.resp.status != 404:
                raise

        pass

    @staticmethod
    def pack(message):
        """ Returns base64 encoded message
        """
        dumped = utils.dumps(message)
        compressed = zlib.compress(dumped.encode('utf8'))
        b64encoded = base64.b64encode(compressed)
        return b64encoded.decode('ascii')

    @staticmethod
    def unpack(message):
        """ Returns a message that been base64 decoded
        """
        b64decoded = base64.b64decode(message)
        uncompressed = zlib.decompress(b64decoded)
        return uncompressed

    """
    Class methods for handling Pub/Sub Subscriptions
    """
    @staticmethod
    def get_subscription_param(session, subscription, project=None):
        """Returns Rest API URI formatted with topic and project in it
        """
        return 'projects/{}/subscriptions/{}'.format(
            project or session.get_default_project(),
            subscription)

    @staticmethod
    def ensure_subscription(session, data, topic=None, subscription=None):
        """Verify the pub/sub topic exists.
        If it does not, create it returns the topic qualified name.
        """

        client = session.client('pubsub', 'v1', 'projects.subscriptions')

        topic = PubSubUtilities.ensure_topic(session, data)
        subscription = PubSubUtilities.get_subscription_param(session, subscription)

        try:
            client.execute_command('get', {'subscription': subscription})
        except HttpError as e:
            if e.resp.status != 404:
                raise
        else:
            return subscription

        # bug in discovery doc.. apis say body must be empty but its required in the
        # discovery api for create.
        client.execute_command('create', {'name': subscription, 'body': {}})
        return topic

        pass

    """
    Class methods for handling Pub/Sub Topics
    """
    @staticmethod
    def get_topic_param(session, data, topic=None, project=None):
        """Returns Rest API URI formatted with topic and project in it
        """
        return 'projects/{}/topics/{}'.format(
            project or session.get_default_project(),
            topic or data['transport']['topic'])

    @staticmethod
    def ensure_topic(session, data):
        """Verify the pub/sub topic exists.
        If it does not, create it

        Returns the topic qualified name.
        """

        client = session.client('pubsub', 'v1', 'projects.topics')

        topic = PubSubUtilities.get_topic_param(session, data)
        try:
            client.execute_command('get', {'topic': topic})
        except HttpError as e:
            if e.resp.status != 404:
                raise
        else:
            return topic

        # bug in discovery doc.. apis say body must be empty but its required in the
        # discovery api for create.
        client.execute_command('create', {'name': topic, 'body': {}})
        return topic

    @staticmethod
    def add(session, data):
        PubSubUtilities.ensure_topic(session, data)

    @staticmethod
    def remove(session, data):
        if not data.get('topic').startswith(data.prefix):
            return
        client = session.client('topic', 'v1', 'projects.topics')
        client.execute_command('delete', {'topic': PubSubUtilities.get_topic_param(session, data)})

    @staticmethod
    def ensure_iam(session, data, publisher=None):
        """ Ensures that the correct Iam Permissions are setup for a topic
        """
        topic = PubSubUtilities.get_topic_param(session, data)
        client = session.client('pubsub', 'v1', 'projects.topics')
        policy = client.execute_command('getIamPolicy', {'resource': topic})
        policy.pop('etag')
        found = False
        for binding in policy.get('bindings', {}):
            if binding['role'] != 'roles/pubsub.publisher':
                continue
            if publisher in binding['members']:
                return
            found = binding

        if not found:
            policy.setdefault(
                'bindings', {'members': [publisher], 'role': 'roles/pubsub.publisher'})
        else:
            found['members'].append(publisher)

        client.execute_command('setIamPolicy', {'resource': topic, 'body': {'policy': policy}})


class SimpleUtc(tzinfo):
    def tzname(self, **kwargs):
        return "UTC"

    def utcoffset(self, dt):
        return timedelta(0)
