# Copyright 2017 Capital One Services, LLC
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

import boto3
import copy
import os
import unittest

import six
from c7n_mailer.email_delivery import EmailDelivery
from common import logger, get_ldap_lookup
from common import MAILER_CONFIG, RESOURCE_1, SQS_MESSAGE_1
from mock import patch, call

# note principalId is very org/domain specific for federated?, it would be good to get
# confirmation from capone on this event / test.
CLOUDTRAIL_EVENT = {
    'detail': {
        'userIdentity': {
            "type": "IAMUser",
            "principalId": "AIDAJ45Q7YFFAREXAMPLE",
            "arn": "arn:aws:iam::123456789012:user/michael_bolton",
            "accountId": "123456789012",
            "accessKeyId": "AKIAIOSFODNN7EXAMPLE",
            "userName": "michael_bolton"
        }
    }
}


class MockEmailDelivery(EmailDelivery):
    def get_ldap_connection(self):
        return get_ldap_lookup(cache_engine='redis')


class EmailTest(unittest.TestCase):

    def setUp(self):
        self.aws_session = boto3.Session()
        self.email_delivery = MockEmailDelivery(MAILER_CONFIG, self.aws_session, logger)
        self.email_delivery.ldap_lookup.uid_regex = ''
        tests_dir = '/tools/c7n_mailer/tests/'
        template_abs_filename = '%s%sexample.jinja' % (os.path.abspath(os.curdir), tests_dir)
        SQS_MESSAGE_1['action']['template'] = template_abs_filename

    def test_valid_email(self):
        self.assertFalse(self.email_delivery.target_is_email('foobar'))
        self.assertFalse(self.email_delivery.target_is_email('foo@bar'))
        self.assertTrue(self.email_delivery.target_is_email('foo@bar.com'))

    def test_priority_header_is_valid(self):
        self.assertFalse(self.email_delivery.priority_header_is_valid('0'))
        self.assertFalse(self.email_delivery.priority_header_is_valid('-1'))
        self.assertFalse(self.email_delivery.priority_header_is_valid('6'))
        self.assertFalse(self.email_delivery.priority_header_is_valid('sd'))
        self.assertTrue(self.email_delivery.priority_header_is_valid('1'))
        self.assertTrue(self.email_delivery.priority_header_is_valid('5'))

    def test_get_valid_emails_from_list(self):
        list_1 = [
            'michael_bolton@initech.com',
            'lsdk',
            'resource-owner',
            'event-owner',
            'bill@initech.com'
        ]
        valid_emails = self.email_delivery.get_valid_emails_from_list(list_1)
        self.assertEqual(valid_emails, ['michael_bolton@initech.com', 'bill@initech.com'])

    def test_event_owner_ldap_flow(self):
        targets = ['event-owner']
        username = self.email_delivery.get_aws_username_from_event(CLOUDTRAIL_EVENT)
        self.assertEqual(username, 'michael_bolton')
        michael_bolton_email = self.email_delivery.get_event_owner_email(targets, CLOUDTRAIL_EVENT)
        self.assertEqual(michael_bolton_email, ['michael_bolton@initech.com'])

    def test_get_ldap_emails_from_resource(self):
        SQS_MESSAGE_1['action']['email_ldap_username_manager'] = False
        ldap_emails = self.email_delivery.get_ldap_emails_from_resource(
            SQS_MESSAGE_1,
            RESOURCE_1
        )
        self.assertEqual(ldap_emails, ['peter@initech.com'])
        SQS_MESSAGE_1['action']['email_ldap_username_manager'] = True
        ldap_emails = self.email_delivery.get_ldap_emails_from_resource(
            SQS_MESSAGE_1,
            RESOURCE_1
        )
        self.assertEqual(ldap_emails, ['peter@initech.com', 'bill_lumberg@initech.com'])

    def test_email_to_resources_map_with_ldap_manager(self):
        emails_to_resources_map = self.email_delivery.get_email_to_addrs_to_resources_map(
            SQS_MESSAGE_1
        )
        # make sure only 1 email is queued to go out
        self.assertEqual(len(emails_to_resources_map.items()), 1)
        to_emails = ('bill_lumberg@initech.com', 'milton@initech.com', 'peter@initech.com')
        self.assertEqual(emails_to_resources_map, {to_emails: [RESOURCE_1]})

    def test_email_to_email_message_map_without_ldap_manager(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE['policy']['actions'][1].pop('email_ldap_username_manager', None)
        email_addrs_to_email_message_map = self.email_delivery.get_to_addrs_email_messages_map(
            SQS_MESSAGE
        )
        to_emails = ('bill_lumberg@initech.com', 'milton@initech.com', 'peter@initech.com')
        items = list(email_addrs_to_email_message_map.items())
        self.assertEqual(items[0][0], to_emails)
        self.assertEqual(items[0][1]['to'], ', '.join(to_emails))

    def test_smtp_called_once(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        to_addrs_to_email_messages_map = self.email_delivery.get_to_addrs_email_messages_map(
            SQS_MESSAGE
        )
        with patch("smtplib.SMTP") as mock_smtp:
            for email_addrs, mimetext_msg in six.iteritems(to_addrs_to_email_messages_map):
                self.email_delivery.send_c7n_email(SQS_MESSAGE, list(email_addrs), mimetext_msg)

                self.assertEqual(mimetext_msg['X-Priority'], '1 (Highest)')
            # Get instance of mocked SMTP object
            smtp_instance = mock_smtp.return_value
            # Checks the mock has been called at least one time
            self.assertTrue(smtp_instance.sendmail.called)
            # Check the mock has been called only once
            self.assertEqual(smtp_instance.sendmail.call_count, 1)
            # Check the mock' calls are equal to a specific list of calls in a
            # specific order
            to_addrs = ['bill_lumberg@initech.com', 'milton@initech.com', 'peter@initech.com']
            self.assertEqual(
                smtp_instance.sendmail.mock_calls,
                [call(MAILER_CONFIG['from_address'], to_addrs, mimetext_msg.as_string())]
            )

    def test_smtp_called_multiple_times(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE['action'].pop('priority_header', None)
        RESOURCE_2 = {
            'AvailabilityZone': 'us-east-1a',
            'Attachments': [],
            'Tags': [
                {
                    'Value': 'samir@initech.com',
                    'Key': 'SupportEmail'
                }
            ],
            'VolumeId': 'vol-01a0e6ea6b8lsdkj93'
        }
        SQS_MESSAGE['resources'].append(RESOURCE_2)
        to_addrs_to_email_messages_map = self.email_delivery.get_to_addrs_email_messages_map(
            SQS_MESSAGE
        )
        with patch("smtplib.SMTP") as mock_smtp:
            for email_addrs, mimetext_msg in six.iteritems(to_addrs_to_email_messages_map):
                self.email_delivery.send_c7n_email(SQS_MESSAGE, list(email_addrs), mimetext_msg)
                self.assertEqual(mimetext_msg.get('X-Priority'), None)
                # self.assertEqual(mimetext_msg.get('X-Priority'), None)
            # Get instance of mocked SMTP object
            smtp_instance = mock_smtp.return_value
            # Checks the mock has been called at least one time
            self.assertTrue(smtp_instance.sendmail.called)
            # Check the mock has been called only once
            self.assertEqual(smtp_instance.sendmail.call_count, 2)

    def test_emails_resource_mapping_multiples(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE['action'].pop('priority_header', None)
        RESOURCE_2 = {
            'AvailabilityZone': 'us-east-1a',
            'Attachments': [],
            'Tags': [
                {
                    'Value': 'samir@initech.com',
                    'Key': 'SupportEmail'
                }
            ],
            'VolumeId': 'vol-01a0e6ea6b8lsdkj93'
        }
        SQS_MESSAGE['resources'].append(RESOURCE_2)
        emails_to_resources_map = self.email_delivery.get_email_to_addrs_to_resources_map(
            SQS_MESSAGE
        )
        email_1_to_addrs = ('bill_lumberg@initech.com', 'milton@initech.com', 'peter@initech.com')
        email_2_to_addrs = ('samir@initech.com',)
        self.assertEqual(emails_to_resources_map[email_1_to_addrs], [RESOURCE_1])
        self.assertEqual(emails_to_resources_map[email_2_to_addrs], [RESOURCE_2])

    def test_emails_resource_mapping_no_owner(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE['action'].pop('priority_header', None)
        SQS_MESSAGE['action']['owner_absent_contact'] = ['foo@example.com']
        RESOURCE_2 = {
            'AvailabilityZone': 'us-east-1a',
            'Attachments': [],
            'Tags': [
                {
                    'Value': 'peter',
                    'Key': 'CreatorName'
                }
            ],
            'VolumeId': 'vol-01a0e6ea6b89f0099'
        }
        SQS_MESSAGE['resources'] = [RESOURCE_2]
        emails_to_resources_map = self.email_delivery.get_email_to_addrs_to_resources_map(
            SQS_MESSAGE
        )
        email_1_to_addrs = (
            'bill_lumberg@initech.com', 'foo@example.com', 'peter@initech.com'
        )
        self.assertEqual(
            emails_to_resources_map[email_1_to_addrs], [RESOURCE_2]
        )

    def test_no_mapping_if_no_valid_emails(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE['action']['to'].remove('ldap_uid_tags')
        SQS_MESSAGE['resources'][0].pop('Tags', None)
        emails_to_resources_map = self.email_delivery.get_email_to_addrs_to_resources_map(
            SQS_MESSAGE
        )
        self.assertEqual(emails_to_resources_map, {})

    def test_flattened_list_get_resource_owner_emails_from_resource(self):
        RESOURCE_2 = {
            'AvailabilityZone': 'us-east-1a',
            'Attachments': [],
            'Tags': [
                {
                    'Value': '123456',
                    'Key': 'OwnerEmail'
                }
            ],
            'VolumeId': 'vol-01a0e6ea6b8lsdkj93'
        }
        RESOURCE_3 = {
            'AvailabilityZone': 'us-east-1a',
            'Attachments': [],
            'Tags': [
                {
                    'Value': 'milton@initech.com',
                    'Key': 'OwnerEmail'
                }
            ],
            'VolumeId': 'vol-01a0e6ea6b8lsdkj93'
        }

        ldap_emails = self.email_delivery.get_resource_owner_emails_from_resource(
            SQS_MESSAGE_1,
            RESOURCE_2
        )

        self.assertEquals(ldap_emails, ['milton@initech.com'])

        ldap_emails = self.email_delivery.get_resource_owner_emails_from_resource(
            SQS_MESSAGE_1,
            RESOURCE_3
        )

        self.assertEquals(ldap_emails, ['milton@initech.com'])
