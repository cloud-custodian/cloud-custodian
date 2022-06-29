# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


import unittest

import smtplib

from c7n_mailer.smtp_delivery import SmtpDelivery
from mock import patch, call, MagicMock


class SmtpDeliveryTest(unittest.TestCase):
    @patch("smtplib.SMTP")
    def test_no_ssl(self, mock_smtp):
        config = {
            "smtp_server": "server",
            "smtp_port": 25,
            "smtp_ssl": False,
            "smtp_username": None,
            "smtp_password": None,
        }
        d = SmtpDelivery(config, MagicMock(), MagicMock())
        del d

        mock_smtp.assert_has_calls([call("server", 25), call().quit()])

    @patch("c7n_mailer.utils.decrypt", return_value="password")
    @patch("smtplib.SMTP")
    def test_no_ssl_with_credentials(self, mock_smtp, decrypt_mock):
        config = {
            "smtp_server": "server",
            "smtp_port": 25,
            "smtp_ssl": False,
            "smtp_username": "username",
            "smtp_password": "password",
        }
        d = SmtpDelivery(config, MagicMock(), MagicMock())
        del d

        mock_smtp.assert_has_calls(
            [call("server", 25), call().login("username", "password"), call().quit()]
        )

    @patch("smtplib.SMTP")
    def test_with_ssl(self, mock_smtp):
        config = {
            "smtp_server": "server",
            "smtp_port": 25,
            "smtp_ssl": True,
            "smtp_username": None,
            "smtp_password": None,
        }
        d = SmtpDelivery(config, MagicMock(), MagicMock())
        del d

        mock_smtp.assert_has_calls(
            [call("server", 25), call().starttls(), call().ehlo(), call().quit()]
        )

    @patch("c7n_mailer.utils.decrypt", return_value="password")
    @patch("smtplib.SMTP")
    def test_with_ssl_and_credentials(self, mock_smtp, decrypt_mock):
        config = {
            "smtp_server": "server",
            "smtp_port": 25,
            "smtp_ssl": True,
            "smtp_username": "username",
            "smtp_password": "password",
        }
        d = SmtpDelivery(config, MagicMock(), MagicMock())
        del d

        mock_smtp.assert_has_calls(
            [
                call("server", 25),
                call().starttls(),
                call().ehlo(),
                call().login("username", "password"),
                call().quit(),
            ]
        )

    @patch("smtplib.SMTP")
    def test_send_message(self, mock_smtp):
        config = {
            "smtp_server": "server",
            "smtp_port": 25,
            "smtp_ssl": False,
            "smtp_username": None,
            "smtp_password": None,
        }
        d = SmtpDelivery(config, MagicMock(), MagicMock())
        message_mock = MagicMock()
        message_mock.__getitem__.side_effect = lambda x: "t@test.com" if x == "From" else None
        message_mock.as_string.return_value = "mock_text"
        d.send_message(message_mock, ["test1@test.com"])
        del d

        mock_smtp.assert_has_calls(
            [
                call("server", 25),
                call().sendmail("t@test.com", ["test1@test.com"], "mock_text"),
                call().quit(),
            ]
        )

    @patch("smtplib.SMTP")
    def test_smtp_disconnected_del(self, mock_smtp):
        # if the smtp server is already disconnected we shouldnt raise an exception when
        # deleting the connection
        config = {
            "smtp_server": "server",
            "smtp_port": 25,
            "smtp_ssl": False,
            "smtp_username": None,
            "smtp_password": None,
        }
        d = SmtpDelivery(config, MagicMock(), MagicMock())
        d._smtp_connection.quit.side_effect = smtplib.SMTPServerDisconnected
        del d
