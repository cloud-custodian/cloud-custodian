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
import json

import requests
import six
from c7n_mailer.ldap_lookup import Redis
from c7n_mailer.utils import kms_decrypt, get_rendered_jinja
from slackclient import SlackClient


class SlackDelivery(object):

    def __init__(self, config, session, logger):
        if config.get('slack_token'):
            config['slack_token'] = kms_decrypt(config, logger, session, 'slack_token')
            self.client = SlackClient(config['slack_token'])
        self.cache_engine = config.get('cache_engine', None)
        if self.cache_engine == 'redis':
            self.caching = Redis(redis_host=config.get('redis_host'), redis_port=int(config.get('redis_port', 6379)), db=0)
        self.config = config
        self.logger = logger
        self.session = session

    @staticmethod
    def is_deliverable(sqs_message):
        if 'cc-slack' in sqs_message.get('action', ()).get('to', ()):
            return True
        return False

    def get_to_addrs_slack_messages_map(self, sqs_message, email_delivery):
        to_addrs_to_resources_map = email_delivery.get_email_to_addrs_to_resources_map(sqs_message)
        slack_messages = {}

        for to_addrs, resources in six.iteritems(to_addrs_to_resources_map):
            resolved_addrs = self.retrieve_user_im(list(to_addrs))

            if not resolved_addrs:
                continue

            for address, slack_target in resolved_addrs.iteritems():
                slack_messages[address] = get_rendered_jinja(slack_target, sqs_message, resources,
                                                             self.logger, 'slack_template', 'slack_default')

        return slack_messages

    def slack_handler(self, sqs_message, slack_messages):

        for message in slack_messages:
            self.logger.info("Sending account:%s policy:%s %s:%s email:%s to %s" % (
                                 sqs_message.get('account', ''),
                                 sqs_message['policy']['name'],
                                 sqs_message['policy']['resource'],
                                 str(len(sqs_message['resources'])),
                                 sqs_message['action'].get('slack_template', 'slack_default'),
                                 json.loads(slack_messages[message])["channel"])
                            )

            self.send_slack_msg(slack_messages[message])

    def retrieve_user_im(self, email_addresses):
        list = {}
        for address in email_addresses:
            if self.cache_engine and self.caching.get(address):
                    self.logger.debug('Got slack metadata from local cache for: %s' % address)
                    list[address] = self.caching.get(address)
                    continue

            response = self.client.api_call(
                "users.lookupByEmail", email=address)

            if not response["ok"] and "Retry-After" in response["headers"]:
                raise Exception("Slack API timeout.")
            elif not response["ok"] and response["error"] == "invalid_auth":
                raise Exception("Invalid Slack token.")
                return
            elif not response["ok"] and response["error"] == "users_not_found":
                self.logger.info("Slack user ID not found.")
                self.caching.set(address, {})
                continue
            else:
                self.logger.debug("Slack account %s found for user %s", response['user']['enterprise_user']['id'])
                if self.cache_engine:
                    self.logger.debug('Writing user: %s metadata to cache engine.' % address)
                    self.caching.set(address, response['user']['enterprise_user']['id'])

                list[address] = response['user']['enterprise_user']['id']

        return list

    def send_slack_msg(self, message_payload):
        response = requests.post(
            url='https://slack.com/api/chat.postMessage',
            data=message_payload,
            headers={'Content-Type': 'application/json;charset=utf-8',
                       'Authorization': 'Bearer %s' % self.config.get('slack_token')}
        )

        if response.status_code != 200:
            self.logger.info("Error in sending Slack message: %s" % response.json())
            return
