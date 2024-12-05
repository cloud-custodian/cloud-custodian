# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


import smtplib
import c7n_mailer.utils as utils


class SmtpDelivery:
    def __init__(self, config, session, logger):
        smtp_server = config["smtp_server"]
        smtp_port = int(config.get("smtp_port", 25))
        smtp_ssl = bool(config.get("smtp_ssl", True))
        smtp_username = config.get("smtp_username")
        smtp_password = utils.decrypt(config, logger, session, "smtp_password")

        smtp_connection = smtplib.SMTP(smtp_server, smtp_port)
        if smtp_ssl:
            smtp_connection.starttls()
            smtp_connection.ehlo()

        if smtp_username or smtp_password:
            smtp_connection.login(smtp_username, smtp_password)

        self._smtp_connection = smtp_connection

    def __del__(self):
        try:
            self._smtp_connection.quit()
        except smtplib.SMTPServerDisconnected:
            pass

    def send_message(self, message, to_addrs):
        self._smtp_connection.sendmail(message["From"], to_addrs, message.as_string())
