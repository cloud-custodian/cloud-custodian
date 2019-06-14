# Copyright 2019 Microsoft Corporation
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


import unittest

from c7n_mailer.smtp_delivery import SmtpDelivery
from mock import patch, call, MagicMock


class SmtpDeliveryTest(unittest.TestCase):

    @patch('smtplib.SMTP')
    def test_no_ssl(self, mock_smtp):
        config = {
            'smtp_server': 'server',
            'smtp_port': 25,
            'smtp_ssl': False,
            'smtp_username': None,
            'smtp_password': None
        }
        d = SmtpDelivery(config, MagicMock(), MagicMock())
        del d

        mock_smtp.assert_has_calls([call('server', 25),
                                    call().quit()])

    @patch('c7n_mailer.utils.decrypt', return_value='password')
    @patch('smtplib.SMTP')
    def test_no_ssl_with_credentials(self, mock_smtp, decrypt_mock):
        config = {
            'smtp_server': 'server',
            'smtp_port': 25,
            'smtp_ssl': False,
            'smtp_username': 'username',
            'smtp_password': 'test'
        }
        d = SmtpDelivery(config, MagicMock(), MagicMock())
        del d

        mock_smtp.assert_has_calls([call('server', 25),
                                    call().login('username', 'password'),
                                    call().quit()])

    @patch('smtplib.SMTP')
    def test_with_ssl(self, mock_smtp):
        config = {
            'smtp_server': 'server',
            'smtp_port': 25,
            'smtp_ssl': True,
            'smtp_username': None,
            'smtp_password': None
        }
        d = SmtpDelivery(config, MagicMock(), MagicMock())
        del d

        mock_smtp.assert_has_calls([call('server', 25),
                                    call().starttls(),
                                    call().ehlo(),
                                    call().quit()])

    @patch('c7n_mailer.utils.decrypt', return_value='password')
    @patch('smtplib.SMTP')
    def test_with_ssl_and_credentials(self, mock_smtp, decrypt_mock):
        config = {
            'smtp_server': 'server',
            'smtp_port': 25,
            'smtp_ssl': True,
            'smtp_username': 'username',
            'smtp_password': 'test'
        }
        d = SmtpDelivery(config, MagicMock(), MagicMock())
        del d

        mock_smtp.assert_has_calls([call('server', 25),
                                    call().starttls(),
                                    call().ehlo(),
                                    call().login('username', 'password'),
                                    call().quit()])

    @patch('smtplib.SMTP')
    def test_send_message(self, mock_smtp):
        config = {
            'smtp_server': 'server',
            'smtp_port': 25,
            'smtp_ssl': False,
            'smtp_username': None,
            'smtp_password': None
        }
        d = SmtpDelivery(config, MagicMock(), MagicMock())
        message_mock = MagicMock()
        message_mock.__getitem__.side_effect = lambda x: 't@test.com' if x == 'From' else None
        message_mock.as_string.return_value = 'mock_text'
        d.send_message(message_mock,
                       ['test1@test.com'])
        del d

        mock_smtp.assert_has_calls([call('server', 25),
                                    call().sendmail('t@test.com', ['test1@test.com'], 'mock_text'),
                                    call().quit()])
