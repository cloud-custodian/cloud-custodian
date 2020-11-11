# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
from email.mime.text import MIMEText
from email.utils import parseaddr

from .utils import (
    get_message_subject, get_rendered_jinja)

logger = logging.getLogger('c7n_mailer.utils.email')


# Those headers are defined as follows:
#  'X-Priority': 1 (Highest), 2 (High), 3 (Normal), 4 (Low), 5 (Lowest)
#              Non-standard, cf https://people.dsv.su.se/~jpalme/ietf/ietf-mail-attributes.html
#              Set by Thunderbird
#  'X-MSMail-Priority': High, Normal, Low
#              Cf Microsoft https://msdn.microsoft.com/en-us/library/gg671973(v=exchg.80).aspx
#              Note: May increase SPAM level on Spamassassin:
#                    https://wiki.apache.org/spamassassin/Rules/MISSING_MIMEOLE
#  'Priority': "normal" / "non-urgent" / "urgent"
#              Cf https://tools.ietf.org/html/rfc2156#section-5.3.6
#  'Importance': "low" / "normal" / "high"
#              Cf https://tools.ietf.org/html/rfc2156#section-5.3.4
PRIORITIES = {
    '1': {
        'X-Priority': '1 (Highest)',
        'X-MSMail-Priority': 'High',
        'Priority': 'urgent',
        'Importance': 'high',
    },
    '2': {
        'X-Priority': '2 (High)',
        'X-MSMail-Priority': 'High',
        'Priority': 'urgent',
        'Importance': 'high',
    },
    '3': {
        'X-Priority': '3 (Normal)',
        'X-MSMail-Priority': 'Normal',
        'Priority': 'normal',
        'Importance': 'normal',
    },
    '4': {
        'X-Priority': '4 (Low)',
        'X-MSMail-Priority': 'Low',
        'Priority': 'non-urgent',
        'Importance': 'low',
    },
    '5': {
        'X-Priority': '5 (Lowest)',
        'X-MSMail-Priority': 'Low',
        'Priority': 'non-urgent',
        'Importance': 'low',
    }
}


def is_email(target):
    if target is None:
        return False
    if target.startswith('slack://'):
        logger.debug("Slack payload, not an email.")
        return False
    if parseaddr(target)[1] and '@' in target and '.' in target:
        return True
    else:
        return False


def priority_header_is_valid(priority_header, logger):
    try:
        priority_header_int = int(priority_header)
    except ValueError:
        return False
    if priority_header_int and 0 < int(priority_header_int) < 6:
        return True
    else:
        logger.warning('mailer priority_header is not a valid string from 1 to 5')
        return False


def set_mimetext_headers(message, subject, from_addr, to_addrs, cc_addrs, priority, logger):
    """Sets headers on Mimetext message"""

    message['Subject'] = subject
    message['From'] = from_addr
    message['To'] = ', '.join(to_addrs)
    if cc_addrs:
        message['Cc'] = ', '.join(cc_addrs)

    if priority and priority_header_is_valid(priority, logger):
        priority = PRIORITIES[str(priority)].copy()
        for key in priority:
            message[key] = priority[key]

    return message


def get_mimetext_message(config, logger, message, resources, to_addrs):
    body = get_rendered_jinja(
        to_addrs, message, resources, logger,
        'template', 'default', config['templates_folders'])

    email_format = message['action'].get('template_format', None)
    if not email_format:
        email_format = message['action'].get(
            'template', 'default').endswith('html') and 'html' or 'plain'

    return set_mimetext_headers(
        message=MIMEText(body, email_format, 'utf-8'),
        subject=get_message_subject(message),
        from_addr=message['action'].get('from', config['from_address']),
        to_addrs=to_addrs,
        cc_addrs=message['action'].get('cc', []),
        priority=message['action'].get('priority_header', None),
        logger=logger
    )
