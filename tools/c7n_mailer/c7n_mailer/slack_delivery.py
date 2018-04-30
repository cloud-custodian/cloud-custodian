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
import time

import requests
import six
from c7n_mailer.email_delivery import EmailDelivery
from c7n_mailer.ldap_lookup import Redis
from c7n_mailer.utils import kms_decrypt, get_rendered_jinja
from slackclient import SlackClient


class SlackDelivery(object):

    def __init__(self, config, session, logger):
        if config.get('slack_token'):
            config['slack_token'] = kms_decrypt(config, logger, session, 'slack_token')
            self.client = SlackClient(config['slack_token'])
        self.caching = self.cache_factory(config, config.get('cache_engine', None))
        self.config = config
        self.logger = logger
        self.session = session
        self.email_handler = EmailDelivery(config, session, logger)

    def cache_factory(self, config, type):
        if type == 'redis':
            return Redis(redis_host=config.get('redis_host'),
                                 redis_port=int(config.get('redis_port', 6379)), db=0)
        else:
            return None


    def get_to_addrs_slack_messages_map(self, sqs_message):
        to_addrs_to_resources_map = self.email_handler.get_email_to_addrs_to_resources_map(sqs_message)
        slack_messages = {}

        # Check for Slack targets in 'to' action and render appropriate template.
        for target in sqs_message.get('action', ()).get('to'):
            if target == 'slack://owners':
                for to_addrs, resources in six.iteritems(to_addrs_to_resources_map):

                    resolved_addrs = self.retrieve_user_im(list(to_addrs))

                    if not resolved_addrs:
                        continue

                    for address, slack_target in resolved_addrs.iteritems():
                        slack_messages[address] = get_rendered_jinja(slack_target, sqs_message, resources,
                                                                     self.logger, 'slack_template', 'slack_default')
                self.logger.debug("Generating messages for recipient list produced by get_email_to_addrs_to_resources_map.")
            elif target.startswith('slack://') and self.email_handler.target_is_email(target.split('slack://', 1)[1]):
                resolved_addrs = self.retrieve_user_im([target.split('slack://', 1)[1]])
                for address, slack_target in resolved_addrs.iteritems():
                    slack_messages[address] = get_rendered_jinja(
                        slack_target, sqs_message, to_addrs_to_resources_map.values()[0],
                        self.logger, 'slack_template', 'slack_default')
                self.logger.debug("Generating message for specified email target, based on lookup via Slack API.")
            elif target.startswith('slack://#'):
                resolved_addrs = target.split('slack://#', 1)[1]
                slack_messages[resolved_addrs] = get_rendered_jinja(resolved_addrs, sqs_message,
                                                                    to_addrs_to_resources_map.values()[0],
                                                                    self.logger, 'slack_template', 'slack_default')

                self.logger.debug("Generating message for specified Slack channel.")

        return slack_messages

    def slack_handler(self, sqs_message, slack_messages):
        for key, payload in slack_messages.iteritems():
            self.logger.info("Sending account:%s policy:%s %s:%s slack:%s to %s" % (
                sqs_message.get('account', ''),
                sqs_message['policy']['name'],
                sqs_message['policy']['resource'],
                str(len(sqs_message['resources'])),
                sqs_message['action'].get('slack_template', 'slack_default'),
                json.loads(payload)["channel"])
            )

            self.send_slack_msg(payload)

    def retrieve_user_im(self, email_addresses):
        list = {}

        for address in email_addresses:
            if self.caching and self.caching.get(address):
                    self.logger.debug('Got Slack metadata from cache for: %s' % address)
                    list[address] = self.caching.get(address)
                    continue

            response = self.client.api_call(
                "users.lookupByEmail", email=address)

            if not response["ok"] and "Retry-After" in response["headers"]:
                self.logger.info("Slack API rate limiting. Waiting %d seconds") % (int(response.headers['retry-after']))
                time.sleep(int(response.headers['Retry-After']))
                continue
            elif not response["ok"] and response["error"] == "invalid_auth":
                raise Exception("Invalid Slack token.")
            elif not response["ok"] and response["error"] == "users_not_found":
                self.logger.info("Slack user ID not found.")
                if self.caching:
                    self.caching.set(address, {})
                continue
            else:
                self.logger.debug("Slack account %s found for user %s", response['user']['enterprise_user']['id'])
                if self.caching:
                    self.logger.debug('Writing user: %s metadata to cache.' % address)
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

        if not response.json()["ok"] and "Retry-After" in response["headers"]:
            self.logger.info("Slack API rate limiting. Waiting %d seconds") % (int(response.headers['retry-after']))
            time.sleep(int(response.headers['Retry-After']))
            return
        elif response.status_code != 200:
            self.logger.info("Error in sending Slack message: %s" % response.json())
            return
