# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
SQS Message Processing
===============

"""
import base64
import json
import logging
import traceback
import zlib

from .email_delivery import EmailDelivery
from .sns_delivery import SnsDelivery

from c7n_mailer.utils import kms_decrypt

DATA_MESSAGE = "maidmsg/1.0"


class MailerSqsQueueIterator:
    # Copied from custodian to avoid runtime library dependency
    msg_attributes = ['sequence_id', 'op', 'ser']

    def __init__(self, aws_sqs, queue_url, logger, limit=0, timeout=10):
        self.aws_sqs = aws_sqs
        self.queue_url = queue_url
        self.limit = limit
        self.logger = logger
        self.timeout = timeout
        self.messages = []

    # this and the next function make this object iterable with a for loop
    def __iter__(self):
        return self

    def __next__(self):
        if self.messages:
            return self.messages.pop(0)
        response = self.aws_sqs.receive_message(
            QueueUrl=self.queue_url,
            WaitTimeSeconds=self.timeout,
            MaxNumberOfMessages=3,
            MessageAttributeNames=self.msg_attributes,
            AttributeNames=['SentTimestamp']
        )

        msgs = response.get('Messages', [])
        self.logger.debug('Messages received %d', len(msgs))
        for m in msgs:
            self.messages.append(m)
        if self.messages:
            return self.messages.pop(0)
        raise StopIteration()

    next = __next__  # python2.7

    def ack(self, m):
        self.aws_sqs.delete_message(
            QueueUrl=self.queue_url,
            ReceiptHandle=m['ReceiptHandle'])


class MailerSqsQueueProcessor:

    def __init__(self, config, session, logger, max_num_processes=16):
        self.config = config
        self.logger = logger
        self.session = session
        self.max_num_processes = max_num_processes
        self.receive_queue = self.config['queue_url']
        self.endpoint_url = self.config.get('endpoint_url', None)
        if self.config.get('debug', False):
            self.logger.debug('debug logging is turned on from mailer config file.')
            logger.setLevel(logging.DEBUG)

    """
    Cases
    - aws resource is tagged CreatorName: 'milton', ldap_tag_uids has CreatorName,
        we do an ldap lookup, get milton's email and send him an email
    - you put an email in the to: field of the notify of your policy, we send an email
        for all resources enforce by that policy
    - you put an sns topic in the to: field of the notify of your policy, we send an sns
        message for all resources enforce by that policy
    - an lambda enforces a policy based on an event, we lookup the event aws username, get their
        ldap email and send them an email about a policy enforcement (from lambda) for the event
    - resource-owners has a list of tags, SupportEmail, OwnerEmail, if your resources
        include those tags with valid emails, we'll send an email for those resources
        any others
    - resource-owners has a list of tags, SnSTopic, we'll deliver an sns message for
        any resources with SnSTopic set with a value that is a valid sns topic.
    """
    def run(self, parallel=False):
        self.logger.info("Downloading messages from the SQS queue.")
        aws_sqs = self.session.client('sqs', endpoint_url=self.endpoint_url)
        sqs_messages = MailerSqsQueueIterator(aws_sqs, self.receive_queue, self.logger)

        sqs_messages.msg_attributes = ['mtype', 'recipient']
        # lambda doesn't support multiprocessing, so we don't instantiate any mp stuff
        # unless it's being run from CLI on a normal system with SHM
        if parallel:
            import multiprocessing
            process_pool = multiprocessing.Pool(processes=self.max_num_processes)
        for sqs_message in sqs_messages:
            self.logger.debug(
                "Message id: %s received %s" % (
                    sqs_message['MessageId'], sqs_message.get('MessageAttributes', '')))
            msg_kind = sqs_message.get('MessageAttributes', {}).get('mtype')
            if msg_kind:
                msg_kind = msg_kind['StringValue']
            if not msg_kind == DATA_MESSAGE:
                warning_msg = 'Unknown sqs_message or sns format %s' % (sqs_message['Body'][:50])
                self.logger.warning(warning_msg)
            if parallel:
                process_pool.apply_async(self.process_sqs_message, args=sqs_message)
            else:
                self.process_sqs_message(sqs_message)
            self.logger.debug('Processed sqs_message')
            sqs_messages.ack(sqs_message)
        if parallel:
            process_pool.close()
            process_pool.join()
        self.logger.info('No sqs_messages left on the queue, exiting c7n_mailer.')
        return

    # This function when processing sqs messages will only deliver messages over email or sns
    # If you explicitly declare which tags are aws_usernames (synonymous with ldap uids)
    # in the ldap_uid_tags section of your mailer.yml, we'll do a lookup of those emails
    # (and their manager if that option is on) and also send emails there.
    def process_sqs_message(self, encoded_sqs_message):
        body = encoded_sqs_message['Body']
        try:
            body = json.dumps(json.loads(body)['Message'])
        except ValueError:
            pass
        sqs_message = json.loads(zlib.decompress(base64.b64decode(body)))

        self.logger.debug("Got account:%s message:%s %s:%d policy:%s recipients:%s" % (
            sqs_message.get('account', 'na'),
            encoded_sqs_message['MessageId'],
            sqs_message['policy']['resource'],
            len(sqs_message['resources']),
            sqs_message['policy']['name'],
            ', '.join(sqs_message['action'].get('to'))))

        # get the map of email_to_addresses to mimetext messages (with resources baked in)
        # and send any emails (to SES or SMTP) if there are email addresses found
        email_delivery = EmailDelivery(self.config, self.session, self.logger)
        to_addrs_to_email_messages_map = email_delivery.get_to_addrs_email_messages_map(sqs_message)
        for email_to_addrs, mimetext_msg in to_addrs_to_email_messages_map.items():
            email_delivery.send_c7n_email(sqs_message, list(email_to_addrs), mimetext_msg)

        # this sections gets the map of sns_to_addresses to rendered_jinja messages
        # (with resources baked in) and delivers the message to each sns topic
        sns_delivery = SnsDelivery(self.config, self.session, self.logger)
        sns_message_packages = sns_delivery.get_sns_message_packages(sqs_message)
        sns_delivery.deliver_sns_messages(sns_message_packages, sqs_message)

        # this section sends a notification to the resource owner via Slack
        if any(e.startswith('slack') or e.startswith('https://hooks.slack.com/')
                for e in sqs_message.get('action', ()).get('to', []) +
                sqs_message.get('action', ()).get('owner_absent_contact', [])):
            from .slack_delivery import SlackDelivery

            if self.config.get('slack_token'):
                self.config['slack_token'] = \
                    kms_decrypt(self.config, self.logger, self.session, 'slack_token')

            slack_delivery = SlackDelivery(self.config, self.logger, email_delivery)
            slack_messages = slack_delivery.get_to_addrs_slack_messages_map(sqs_message)
            try:
                slack_delivery.slack_handler(sqs_message, slack_messages)
            except Exception:
                traceback.print_exc()
                pass

        # this section gets the map of metrics to send to datadog and delivers it
        if any(e.startswith('datadog') for e in sqs_message.get('action', ()).get('to')):
            from .datadog_delivery import DataDogDelivery
            datadog_delivery = DataDogDelivery(self.config, self.session, self.logger)
            datadog_message_packages = datadog_delivery.get_datadog_message_packages(sqs_message)

            try:
                datadog_delivery.deliver_datadog_messages(datadog_message_packages, sqs_message)
            except Exception:
                traceback.print_exc()
                pass

        # this section sends the full event to a Splunk HTTP Event Collector (HEC)
        if any(
            e.startswith('splunkhec://')
            for e in sqs_message.get('action', ()).get('to')
        ):
            from .splunk_delivery import SplunkHecDelivery
            splunk_delivery = SplunkHecDelivery(self.config, self.session, self.logger)
            splunk_messages = splunk_delivery.get_splunk_payloads(
                sqs_message, encoded_sqs_message['Attributes']['SentTimestamp']
            )

            try:
                splunk_delivery.deliver_splunk_messages(splunk_messages)
            except Exception:
                traceback.print_exc()
                pass
