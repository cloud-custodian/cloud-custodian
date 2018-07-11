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

import sendgrid
import six
from python_http_client import exceptions
from sendgrid.helpers.mail import Email, Content, Mail

from c7n_mailer.utils import (
    get_message_subject, get_rendered_jinja)


class SendGridDelivery(object):

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.sendgrid_client = sendgrid.SendGridAPIClient(apikey=self.config['sendgrid_api_key'])

    def get_to_addrs_sendgrid_messages_map(self, queue_message):
        targets = queue_message['action']['to']

        # eg: { ('milton@initech.com', 'peter@initech.com'): [resource1, resource2, etc] }
        to_addrs_to_resources_map = {tuple(sorted(set(targets))): queue_message['resources']}

        to_addrs_to_content_map = {}
        for to_addrs, resources in six.iteritems(to_addrs_to_resources_map):
            to_addrs_to_content_map[to_addrs] = self.get_message_content(
                queue_message,
                resources,
                list(to_addrs)
            )
        # eg: { ('milton@initech.com', 'peter@initech.com'): message }
        return to_addrs_to_content_map

    def get_message_content(self, queue_message, resources, to_addrs):
        return get_rendered_jinja(
            to_addrs, queue_message, resources, self.logger, 'template', 'default')

    def sendgrid_handler(self, queue_message, to_addrs_to_email_messages_map):
        self.logger.info("Sending account:%s policy:%s %s:%s email:%s to %s" % (
            queue_message.get('account', ''),
            queue_message['policy']['name'],
            queue_message['policy']['resource'],
            str(len(queue_message['resources'])),
            queue_message['action'].get('template', 'default'),
            to_addrs_to_email_messages_map))

        from_email = Email(self.config['from_address'])
        subject = get_message_subject(queue_message)
        email_format = queue_message['action'].get('template_format', None)
        if not email_format:
            email_format = queue_message['action'].get(
                'template', 'default').endswith('html') and 'html' or 'plain'

        for email_to_addrs, email_content in six.iteritems(to_addrs_to_email_messages_map):
            for to_address in email_to_addrs:
                to_email = Email(to_address)
                content = Content("text/" + email_format, email_content)
                mail = Mail(from_email, subject, to_email, content)
                try:
                    self.sendgrid_client.client.mail.send.post(request_body=mail.get())
                except (exceptions.UnauthorizedError, exceptions.BadRequestsError) as e:
                    self.logger.warning(
                        "\n**Error \nPolicy:%s \nAccount:%s \nSending to:%s \n\nRequest body:"
                        "\n%s\n\nRequest headers:\n%s\n\n mailer.yml: %s" % (
                            queue_message['policy'],
                            queue_message.get('account', ''),
                            email_to_addrs,
                            e.body,
                            e.headers,
                            self.config
                        )
                    )
                    return False
        return True
