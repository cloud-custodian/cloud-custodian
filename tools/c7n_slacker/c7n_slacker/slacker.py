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
from slackclient import SlackClient
from tenacity import retry, stop_after_attempt, wait_fixed


class SlackBot(object):

    def __init__(self, token, logger):
        self.client = SlackClient(token)
        self.logger = logger

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(2))
    def slack_handler(self, resource_dict):
        response = self.retrieve_user_im(resource_dict['resource_owner_value'])

        if not response["ok"] and "Retry-After" in response["headers"]:
            raise Exception("Slack API timeout.")
        elif not response["ok"] and response["error"] == "users_not_found":
            self.logger.info("Slack user ID not found.")
            return
        else:
            self.logger.debug("Slack account %s found for user %s", response['user']['enterprise_user']['id'],
                              resource_dict['resource_owner_value'])
            self.send_slack_msg(response['user']['enterprise_user']['id'], resource_dict)

    def retrieve_user_im(self, user_email):
        response = self.client.api_call(
                    "users.lookupByEmail", email=user_email)
        return response

    def send_slack_msg(self, channel, resource_dict):
        self.client.api_call(
            "chat.postMessage", channel=channel,
            text='Account Name: {r[account]} Region: {r[region]}\nCompliance Status: \
            {r[violation_desc]}\n{r[resource_string]}\n{r[action_desc]}'.format(r=resource_dict))
