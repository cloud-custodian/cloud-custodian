import json
from email.utils import getaddresses, parseaddr

import requests

from .utils import decrypt


class GraphDelivery:
    def __init__(self, config, session, logger):
        self.token = self.get_token(
            config["graph_token_endpoint"],
            config["graph_client_id"],
            decrypt(config, logger, session, "graph_client_secret"),
        )
        self.session = session
        self.sendmail_endpoint = config["graph_sendmail_endpoint"]
        self.logger = logger

    def send_message(self, emails_to_mimetext_map):
        headers = {
            "Authorization": "Bearer " + self.token,
            "Content-type": "application/json",
        }
        # NOTE emails_to_mimetext_map: dict[tuple, MIMEText]; removed it from sinature for py3.8
        for emails, mimetext in emails_to_mimetext_map.items():
            contentType = mimetext.get_content_type().lower().endswith("html") and "html" or "text"
            content = mimetext.get_payload(decode=True).decode(mimetext.get_content_charset())
            # cc addresses are in emails but not in the To header, see get_mimetext_message
            to_header = {addr for _, addr in getaddresses(mimetext.get_all("To", []))}
            # reference: https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0
            data = {
                "message": {
                    "subject": mimetext.get("Subject"),
                    "body": {"contentType": contentType, "content": content},
                    "toRecipients": [
                        {"emailAddress": {"address": e}}
                        for e in emails
                        if parseaddr(e)[1] in to_header
                    ],
                    "ccRecipients": [
                        {"emailAddress": {"address": e}}
                        for e in emails
                        if parseaddr(e)[1] not in to_header
                    ],
                },
                "isDraft": "false",
            }
            r = requests.post(
                self.sendmail_endpoint, data=json.dumps(data), headers=headers, timeout=10
            )
            r.raise_for_status()

    def get_token(self, url, client_id, client_secret):
        data = {
            "grant_type": "client_credentials",
            "scope": "https://graph.microsoft.com/.default",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        r = requests.post(url, data=data, timeout=10)
        r.raise_for_status()
        return r.json().get("access_token")
