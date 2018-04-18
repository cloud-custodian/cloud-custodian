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
import base64
import json
import os
import zlib
from email.utils import parseaddr

import boto3
from botocore.exceptions import ClientError
from concurrent.futures import ThreadPoolExecutor, as_completed
from ldap3 import Connection, Server
from ldap3.core.exceptions import LDAPSocketOpenError

from c7n import sqsexec, utils

from slacker import NotifyMechanism


class SQSHandler(object):

    def __init__(self, config, logger):
        self.config = config
        self.session = self.session_factory(self.config)
        self.logger = logger
        self.base_dn = self.config.get('ldap_bind_dn')
        self.email_key = self.config.get('ldap_email_key', 'mail')
        self.uid_key = self.config.get('ldap_uid_attribute_name', 'sAMAccountName')
        self.manager_attr = self.config.get('ldap_manager_attribute', 'manager')
        self.attributes = ['displayName', self.uid_key, self.email_key, self.manager_attr]

    def message_handler(self, connection, config, msg):
        message = msg['Body']
        try:
            msg_json = json.loads(zlib.decompress(base64.b64decode(message)))
            self.logger.info(
                "Acct: %s,  msg: %s, resource type: %s, count: %d, policy: %s, \
                recipients: %s, action_desc: %s, violation_desc: %s" % (
                    msg_json.get('account', 'na'),
                    msg['MessageId'],
                    msg_json['policy']['resource'],
                    len(msg_json['resources']),
                    msg_json['policy']['name'],
                    ', '.join(msg_json['action']['to']),
                    msg_json['action']['action_desc'],
                    msg_json['action']['violation_desc']))
            self.logger.debug('Valid JSON')
        except ValueError:
            self.logger.warning("Invalid JSON")
            return

        if 'resource-owner' not in msg_json['action']['to']:
            self.logger.debug("Resource owner indicator not found. Skipping message.")
            return

        resource_dict = {'account': msg_json['account'], 'account_id': msg_json['account_id'],
                         'region': msg_json['region'], 'action_desc': msg_json['action']['action_desc'],
                         'violation_desc': msg_json['action']['violation_desc']}

        for resource in msg_json['resources']:
            try:
                resource_owner_value, matched_tag = self.get_resource_owner_values(resource)
            except Exception as e:
                self.logger.debug("Error fetching resource owner value: %s" % e)
                continue

            if resource_owner_value is None:
                self.logger.debug("Resource details not found. Skipping message....")
                continue
            else:
                resource_string = utils.resource_format(resource, msg_json['policy']['resource'])
                self.logger.debug("resource string: %s", resource_string)

                if (self.target_is_email(resource_owner_value)):
                    self.logger.debug("%s %s: %s" % (resource_string, matched_tag, resource_owner_value))
                    self.logger.debug("Email address found.")
                elif "arn:aws:sns" in resource_owner_value:
                    self.logger.debug("Contact method is SNS topic. Skipping.")
                    continue
                else:
                    self.logger.debug("ID number found. Doing LDAP lookup.")
                    ldap_filter = '(%s=%s)' % (self.uid_key, resource_owner_value)
                    connection.search(self.base_dn, ldap_filter, attributes=self.attributes)
                    if len(connection.entries) == 0:
                        self.logger.warning("User not found. base_dn: %s filter: %s", self.base_dn, ldap_filter)
                        continue
                    elif len(connection.entries) > 1:
                        self.logger.warning("Multiple results returned.")
                        continue
                    else:
                        resource_owner_value = connection.entries[0]['mail']

            self.logger.debug("%s %s" % (resource_owner_value, resource_string))

            resource_dict['resource_owner_value'] = resource_owner_value
            resource_dict['resource_string'] = resource_string

            for method in config.get('notify_methods'):
                notify_obj = NotifyMechanism.factory(method, config, self.logger)
                notify_obj.notify_handler(resource_dict)

    def process_sqs(self, config):

        sqs_fetch = sqsexec.MessageIterator(client=self.session.client('sqs'),
                                            queue_url=self.config.get('queue_url'), timeout=0)
        connection = self.get_ldap_session()
        self.logger.info('Processing queue messages')

        for m in sqs_fetch:

            with ThreadPoolExecutor(max_workers=2) as w:
                futures = {w.submit(self.message_handler, connection, config, m): m}

                for future in as_completed(futures):
                    # sqs_fetch.ack(m)
                    if future.exception():
                        self.logger.error("Error processing message: %s", future.exception())

    @staticmethod
    def session_factory(config):

        if config.get('region') is None:
            set_region = os.environ['AWS_DEFAULT_REGION']
        else:
            set_region = config.get('region')

        if config.get('profile') is None:
            set_profile = os.environ['AWS_DEFAULT_PROFILE']
        else:
            set_profile = config.get('profile')

        return boto3.Session(
            region_name=set_region,
            profile_name=set_profile)

    def get_resource_owner_values(self, sqs_message):
        if 'Tags' in sqs_message:
            tags = {tag['Key']: tag['Value'] for tag in sqs_message['Tags']}
        else:
            self.logger.debug("No tags found on resource. Skipping")
            return None, None

        if tags:
            for contact_tag in self.config.get('contact_tags'):
                if tags.get(contact_tag, None):
                        self.logger.info("Resource owner match: %s - %s", contact_tag, tags[contact_tag])
                        return tags[contact_tag], contact_tag
        else:
            self.logger.debug("No tags found.")
            return None, None

    @staticmethod
    def target_is_email(target):
        if parseaddr(target)[1] and '@' in target and '.' in target:
            return True
        return False

    def get_ldap_session(self):
        try:
            if self.config.get('ldap_bind_password', None):
                ldap_bind_password = self.session.client('kms').decrypt(
                    CiphertextBlob=base64.b64decode(self.config.get('ldap_bind_password')))[
                    'Plaintext']
        except (TypeError, base64.binascii.Error) as e:
            self.logger.warning(
                "Error: %s Unable to base64 decode ldap_bind_password, will assume plaintext." % e
            )
        except ClientError as e:
            if e.response['Error']['Code'] != 'InvalidCiphertextException':
                raise
            self.logger.warning(
                "Error: %s Unable to decrypt ldap_bind_password with kms, will assume plaintext." % e
            )
        try:
            server = Server(self.config.get('ldap_uri'), use_ssl=True)
            return Connection(
                server, user=self.config.get('ldap_bind_user'), password=ldap_bind_password,
                auto_bind=True,
                receive_timeout=30,
                auto_referrals=False
            )
        except LDAPSocketOpenError:
            self.logger.error('Not able to establish a connection with LDAP.')
