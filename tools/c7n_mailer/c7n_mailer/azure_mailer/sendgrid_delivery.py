# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


import sendgrid
from python_http_client import exceptions
from sendgrid.helpers.mail import Content, Email, Header, Mail, To

from c7n_mailer.utils import decrypt
from c7n_mailer.utils_email import get_mimetext_message, is_email


class SendGridDelivery:
    def __init__(self, config, session, logger):
        self.config = config
        self.logger = logger
        self.session = session
        api_key = decrypt(self.config, self.logger, self.session, "sendgrid_api_key")
        self.sendgrid_client = sendgrid.SendGridAPIClient(api_key)

    def get_to_addrs_sendgrid_messages_map(self, queue_message):
        # eg: { ('milton@initech.com', 'peter@initech.com'): [resource1, resource2, etc] }
        to_addrs_to_resources_map = self.get_emails_to_resources_map(queue_message)

        to_addrs_to_content_map = {}
        for to_addrs, resources in to_addrs_to_resources_map.items():
            to_addrs_to_content_map[to_addrs] = get_mimetext_message(
                self.config, self.logger, queue_message, resources, list(to_addrs)
            )
        # eg: { ('milton@initech.com', 'peter@initech.com'): message }
        return to_addrs_to_content_map

    # this function returns a dictionary with a tuple of emails as the key
    # and the list of resources as the value. This helps ensure minimal emails
    # are sent, while only ever sending emails to the respective parties.
    def get_emails_to_resources_map(self, queue_message):
        email_to_addrs_to_resources_map = {}
        targets = queue_message["action"].get("to", [])

        for resource in queue_message["resources"]:
            # this is the list of emails that will be sent for this resource
            resource_emails = []

            for target in targets:
                if target.startswith("tag:") and "tags" in resource:
                    tag_name = target.split(":", 1)[1]
                    result = resource.get("tags", {}).get(tag_name, None)
                    if is_email(result):
                        resource_emails.append(result)
                elif is_email(target):
                    resource_emails.append(target)

            resource_emails = tuple(sorted(set(resource_emails)))

            if resource_emails:
                email_to_addrs_to_resources_map.setdefault(resource_emails, []).append(resource)

        if email_to_addrs_to_resources_map == {}:
            self.logger.debug("Found no email addresses, sending no emails.")
        # eg: { ('milton@initech.com', 'peter@initech.com'): [resource1, resource2, etc] }
        return email_to_addrs_to_resources_map

    def sendgrid_handler(self, queue_message, emails_to_mimetext_map):
        self.logger.info(
            "Sending account:%s policy:%s %s:%s email:%s to %s"
            % (
                queue_message.get("account", ""),
                queue_message["policy"]["name"],
                queue_message["policy"]["resource"],
                str(len(queue_message["resources"])),
                queue_message["action"].get("template", "default"),
                emails_to_mimetext_map,
            )
        )

        for email_to_addrs, mimetext in emails_to_mimetext_map.items():
            for to_address in email_to_addrs:
                try:
                    mail = SendGridDelivery._construct_mail_from_mimetext(mimetext, to_address)
                    self.sendgrid_client.send(mail)
                except (exceptions.UnauthorizedError, exceptions.BadRequestsError) as e:
                    self.logger.warning(
                        "\n**Error \nPolicy:%s \nAccount:%s \nSending to:%s \n\nRequest body:"
                        "\n%s\n\nRequest headers:\n%s\n\n mailer.yml: %s"
                        % (
                            queue_message["policy"],
                            queue_message.get("account", ""),
                            email_to_addrs,
                            e.body,
                            e.headers,
                            self.config,
                        )
                    )
                    return False
        return True

    @staticmethod
    def _construct_mail_from_mimetext(message, to_address) -> Mail:
        """
        Create a Mail object from an instance of email.message.EmailMessage.

        This is a copy and tweak of Mail.from_EmailMessage from the SendGrid SDK
        to get around a bug where it creates an Email object and later requires
        that object to be an instance of a To, Cc, or Bcc object.

        It also strips out any reserved key headers on the message object.
        """

        mail = Mail(
            from_email=Email(message.get("From")),
            subject=message.get("Subject"),
            # Create a To object instead of an Email object
            to_emails=To(to_address),
        )
        try:
            body = message.get_content()
        except AttributeError:
            # Python2
            body = message.get_payload(decode=True).decode("utf-8")
        mail.add_content(Content(message.get_content_type(), body.strip()))

        # These headers are not allowed on the message object
        # https://sendgrid.com/docs/API_Reference/Web_API_v3/Mail/errors.html#message.headers
        skip_headers = [
            "x-sg-id",
            "x-sg-eid",
            "received",
            "dkim-signature",
            "Content-Type",
            "Content-Transfer-Encoding",
            "To",
            "From",
            "Subject",
            "Reply-To",
            "CC",
            "BCC",
        ]

        for k, v in message.items():
            if k not in skip_headers:
                mail.add_header(Header(k, v))
        return mail
